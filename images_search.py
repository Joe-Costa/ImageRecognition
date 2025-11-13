#!/usr/bin/env python3
"""
CPU-only image indexing & semantic search using CLIP via sentence-transformers.

Usage:

  # 1) Index a directory of images
  python image_search.py index \
      --image-dir ./images \
      --index-prefix ./image_index

  # This will create:
  #   ./image_index.parquet  (paths + embeddings)
  #   ./image_index.faiss    (Faiss vector index)
  #   ./image_index.meta.json (metadata: model name, dim)

  # 2) Run a text query against the index
  python image_search.py query \
      --index-prefix ./image_index \
      --text "a yellow car" \
      --top-k 10

"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List

import numpy as np
import polars as pl
from PIL import Image

import faiss
from sentence_transformers import SentenceTransformer

# --------- Config defaults --------- #

DEFAULT_MODEL_NAME = "clip-ViT-B-32"
DEFAULT_BATCH_SIZE = 16
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"}


# --------- Utility functions --------- #


def find_images(root: Path) -> List[Path]:
    """Recursively find image files under root with known extensions."""
    images: List[Path] = []
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            ext = Path(name).suffix.lower()
            if ext in VALID_EXTENSIONS:
                images.append(Path(dirpath) / name)
    return images


def load_image(path: Path) -> Image.Image:
    """Load an image as RGB, or raise on error."""
    img = Image.open(path)
    return img.convert("RGB")


def save_metadata(meta_path: Path, data: dict) -> None:
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_metadata(meta_path: Path) -> dict:
    with meta_path.open("r", encoding="utf-8") as f:
        return json.load(f)


# --------- Indexing --------- #


def cmd_index(args: argparse.Namespace) -> None:
    image_dir = Path(args.image_dir).expanduser().resolve()
    prefix = Path(args.index_prefix).expanduser().resolve()

    if not image_dir.is_dir():
        print(f"ERROR: image directory not found: {image_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"[index] Scanning for images under: {image_dir}")
    images = find_images(image_dir)
    if not images:
        print(
            "ERROR: no images found. Supported extensions:",
            ", ".join(sorted(VALID_EXTENSIONS)),
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[index] Found {len(images)} image(s).")

    # Load CLIP model on CPU
    print(f"[index] Loading model: {args.model_name} (device=cpu)")
    model = SentenceTransformer(args.model_name, device="cpu")

    # Encode images in batches
    all_paths: List[str] = []
    all_embs: List[np.ndarray] = []

    batch_size = args.batch_size
    total = len(images)
    print(f"[index] Encoding images in batches of {batch_size}...")

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch_paths = images[start:end]

        batch_imgs = []
        for p in batch_paths:
            try:
                img = load_image(p)
                batch_imgs.append(img)
            except Exception as e:  # noqa: BLE001
                print(f"[index] WARNING: failed to load {p}: {e}", file=sys.stderr)

        if not batch_imgs:
            continue

        # SentenceTransformers will handle batching internally as well, but we pass our own batch.
        embs = model.encode(
            batch_imgs,
            batch_size=len(batch_imgs),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        # embs: (batch, dim)
        for p, emb in zip(batch_paths, embs):
            all_paths.append(str(p))
            all_embs.append(emb.astype("float32"))

        print(f"[index] Processed {end}/{total} images...", end="\r", flush=True)

    print()  # newline after progress

    if not all_embs:
        print("ERROR: no embeddings generated; all images failed?", file=sys.stderr)
        sys.exit(1)

    embeddings = np.stack(all_embs, axis=0)  # (N, D)
    dim = embeddings.shape[1]
    print(
        f"[index] Generated embeddings for {embeddings.shape[0]} images with dim={dim}."
    )

    # Save as Parquet (paths + embedding list)
    df = pl.DataFrame(
        {
            "path": all_paths,
            "embedding": [emb.tolist() for emb in embeddings],
        }
    )

    parquet_path = prefix.with_suffix(".parquet")
    print(f"[index] Writing Parquet index to: {parquet_path}")
    df.write_parquet(parquet_path)

    # Build Faiss index (Inner Product because we normalized embeddings)
    print("[index] Building Faiss index (IndexFlatIP)...")
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    faiss_path = prefix.with_suffix(".faiss")
    print(f"[index] Saving Faiss index to: {faiss_path}")
    faiss.write_index(index, str(faiss_path))

    # Save metadata
    meta = {
        "model_name": args.model_name,
        "embedding_dim": dim,
        "num_images": int(embeddings.shape[0]),
        "image_dir": str(image_dir),
        "paths_relative_to": None,  # reserved if you later want to store relative paths
    }
    meta_path = prefix.with_suffix(".meta.json")
    print(f"[index] Writing metadata to: {meta_path}")
    save_metadata(meta_path, meta)

    print("[index] Done.")


# --------- Querying --------- #


def cmd_query(args: argparse.Namespace) -> None:
    prefix = Path(args.index_prefix).expanduser().resolve()

    parquet_path = prefix.with_suffix(".parquet")
    faiss_path = prefix.with_suffix(".faiss")
    meta_path = prefix.with_suffix(".meta.json")

    if (
        not parquet_path.is_file()
        or not faiss_path.is_file()
        or not meta_path.is_file()
    ):
        print(
            f"ERROR: index files not found for prefix {prefix}.\n"
            f"Expected: {parquet_path}, {faiss_path}, {meta_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load metadata
    meta = load_metadata(meta_path)
    model_name = meta.get("model_name", DEFAULT_MODEL_NAME)
    dim = int(meta.get("embedding_dim"))
    print(f"[query] Using model '{model_name}' with dim={dim}")

    # Load table
    print(f"[query] Loading Parquet index from: {parquet_path}")
    df = pl.read_parquet(parquet_path)
    paths = df["path"].to_list()
    emb_list = df["embedding"].to_list()
    embeddings = np.array(emb_list, dtype="float32")
    if embeddings.shape[1] != dim:
        print(
            f"ERROR: embedding dimension mismatch: meta says {dim}, "
            f"but Parquet has {embeddings.shape[1]}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load Faiss index
    print(f"[query] Loading Faiss index from: {faiss_path}")
    index = faiss.read_index(str(faiss_path))

    if index.d != dim:
        print(
            f"ERROR: Faiss index dimension mismatch: index.d={index.d}, meta.dim={dim}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load model (CPU)
    print(f"[query] Loading model: {model_name} (device=cpu)")
    model = SentenceTransformer(model_name, device="cpu")

    query_text = args.text
    print(f"[query] Encoding text query: {query_text!r}")
    q_emb = model.encode(
        query_text,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype("float32")

    # Ensure shape (1, dim)
    q_emb = q_emb.reshape(1, -1)

    top_k = args.top_k
    print(f"[query] Searching top-{top_k}...")
    scores, indices = index.search(q_emb, top_k)

    print("\n[query] Results:")
    for rank, (score, idx) in enumerate(zip(scores[0], indices[0]), start=1):
        if idx < 0 or idx >= len(paths):
            continue
        print(f"{rank:2d}. score={score:.4f}  path={paths[idx]}")


# --------- Main CLI --------- #


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="CPU-only CLIP-based image indexing and search."
    )
    sub = p.add_subparsers(dest="command", required=True)

    # index command
    pi = sub.add_parser("index", help="Index a directory of images.")
    pi.add_argument(
        "--image-dir",
        required=True,
        help="Directory containing images (recursively scanned).",
    )
    pi.add_argument(
        "--index-prefix",
        required=True,
        help="Prefix for index files, e.g. ./image_index (creates .parquet, .faiss, .meta.json).",
    )
    pi.add_argument(
        "--model-name",
        default=DEFAULT_MODEL_NAME,
        help=f"SentenceTransformers CLIP model name (default: {DEFAULT_MODEL_NAME})",
    )
    pi.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Batch size for encoding images (default: {DEFAULT_BATCH_SIZE})",
    )
    pi.set_defaults(func=cmd_index)

    # query command
    pq = sub.add_parser(
        "query", help="Query an existing image index with a text prompt."
    )
    pq.add_argument(
        "--index-prefix",
        required=True,
        help="Same prefix used in 'index' step, e.g. ./image_index.",
    )
    pq.add_argument(
        "--text",
        required=True,
        help="Text query, e.g. 'a yellow car' or 'a hot dog'.",
    )
    pq.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of results to return (default: 10).",
    )
    pq.set_defaults(func=cmd_query)

    return p


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
