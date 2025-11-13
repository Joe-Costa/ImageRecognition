#!/usr/bin/env python3
"""
Worker script for distributed image indexing using CLIP.

This script processes a subset of images assigned to it by the controller
and generates partial index files that can be merged later.

Usage:
  python worker_index.py \
      --image-list ./worker_images.txt \
      --index-prefix /mnt/music/home/joe/imageindex/worker_0 \
      --worker-id 0 \
      --batch-size 8
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List

import numpy as np
import polars as pl
from PIL import Image

import faiss
from sentence_transformers import SentenceTransformer

# --------- Config defaults --------- #

DEFAULT_MODEL_NAME = "clip-ViT-B-32"
DEFAULT_BATCH_SIZE = 8
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"}


# --------- Utility functions --------- #


def load_image(path: Path) -> Image.Image:
    """Load an image as RGB, or raise on error."""
    img = Image.open(path)
    return img.convert("RGB")


def save_metadata(meta_path: Path, data: dict) -> None:
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def log(msg: str, worker_id: int) -> None:
    """Log message with timestamp and worker ID."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [Worker {worker_id}] {msg}", flush=True)


# --------- Worker Indexing --------- #


def cmd_worker_index(args: argparse.Namespace) -> None:
    worker_id = args.worker_id
    image_list_path = Path(args.image_list).expanduser().resolve()
    prefix = Path(args.index_prefix).expanduser().resolve()

    log(f"Starting worker indexing", worker_id)
    log(f"Image list: {image_list_path}", worker_id)
    log(f"Index prefix: {prefix}", worker_id)

    if not image_list_path.is_file():
        log(f"ERROR: image list file not found: {image_list_path}", worker_id)
        sys.exit(1)

    # Load image paths from file
    with image_list_path.open("r") as f:
        image_paths = [Path(line.strip()) for line in f if line.strip()]

    if not image_paths:
        log("ERROR: no images found in list file", worker_id)
        sys.exit(1)

    log(f"Loaded {len(image_paths)} image(s) to process", worker_id)

    # Load CLIP model on CPU
    log(f"Loading model: {args.model_name} (device=cpu)", worker_id)
    model = SentenceTransformer(args.model_name, device="cpu")

    # Encode images in batches
    all_paths: List[str] = []
    all_embs: List[np.ndarray] = []

    batch_size = args.batch_size
    total = len(image_paths)
    log(f"Encoding images in batches of {batch_size}...", worker_id)

    processed = 0
    failed = 0
    start_time = time.time()

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch_paths = image_paths[start:end]

        batch_imgs = []
        batch_valid_paths = []
        for p in batch_paths:
            try:
                img = load_image(p)
                batch_imgs.append(img)
                batch_valid_paths.append(p)
            except Exception as e:
                log(f"WARNING: failed to load {p}: {e}", worker_id)
                failed += 1

        if not batch_imgs:
            continue

        # Encode batch
        try:
            embs = model.encode(
                batch_imgs,
                batch_size=len(batch_imgs),
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )

            # embs: (batch, dim)
            for p, emb in zip(batch_valid_paths, embs):
                all_paths.append(str(p))
                all_embs.append(emb.astype("float32"))

            processed += len(batch_imgs)

            # Progress update
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (total - end) / rate if rate > 0 else 0
            log(
                f"Progress: {end}/{total} images "
                f"({100*end/total:.1f}%) - "
                f"{rate:.1f} img/s - "
                f"ETA: {eta/60:.1f}min",
                worker_id
            )
        except Exception as e:
            log(f"ERROR: failed to encode batch: {e}", worker_id)
            failed += len(batch_imgs)

    total_time = time.time() - start_time
    log(
        f"Encoding complete: {processed} succeeded, {failed} failed "
        f"in {total_time/60:.1f} minutes",
        worker_id
    )

    if not all_embs:
        log("ERROR: no embeddings generated; all images failed", worker_id)
        sys.exit(1)

    embeddings = np.stack(all_embs, axis=0)  # (N, D)
    dim = embeddings.shape[1]
    log(f"Generated embeddings for {embeddings.shape[0]} images with dim={dim}", worker_id)

    # Create output directory if needed
    prefix.parent.mkdir(parents=True, exist_ok=True)

    # Save as Parquet (paths + embedding list)
    df = pl.DataFrame(
        {
            "path": all_paths,
            "embedding": [emb.tolist() for emb in embeddings],
        }
    )

    parquet_path = prefix.with_suffix(".parquet")
    log(f"Writing Parquet index to: {parquet_path}", worker_id)
    df.write_parquet(parquet_path)

    # Build Faiss index (Inner Product because we normalized embeddings)
    log("Building Faiss index (IndexFlatIP)...", worker_id)
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    faiss_path = prefix.with_suffix(".faiss")
    log(f"Saving Faiss index to: {faiss_path}", worker_id)
    faiss.write_index(index, str(faiss_path))

    # Save metadata
    meta = {
        "worker_id": worker_id,
        "model_name": args.model_name,
        "embedding_dim": dim,
        "num_images": int(embeddings.shape[0]),
        "num_failed": failed,
        "processing_time_seconds": total_time,
        "batch_size": batch_size,
    }
    meta_path = prefix.with_suffix(".meta.json")
    log(f"Writing metadata to: {meta_path}", worker_id)
    save_metadata(meta_path, meta)

    log("Worker indexing complete!", worker_id)


# --------- Main CLI --------- #


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Worker script for distributed CLIP-based image indexing."
    )

    p.add_argument(
        "--image-list",
        required=True,
        help="Path to text file containing image paths (one per line).",
    )
    p.add_argument(
        "--index-prefix",
        required=True,
        help="Prefix for output index files (e.g., /path/to/worker_0).",
    )
    p.add_argument(
        "--worker-id",
        type=int,
        required=True,
        help="Unique worker ID (used for logging).",
    )
    p.add_argument(
        "--model-name",
        default=DEFAULT_MODEL_NAME,
        help=f"SentenceTransformers CLIP model name (default: {DEFAULT_MODEL_NAME})",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Batch size for encoding images (default: {DEFAULT_BATCH_SIZE})",
    )

    return p


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    cmd_worker_index(args)


if __name__ == "__main__":
    main()
