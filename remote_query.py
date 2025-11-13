#!/usr/bin/env python3
"""
Remote query script - runs on worker hosts.

This script performs semantic image search queries using the indexed embeddings
and copies matching images to a results directory with timestamped names.

Usage (on worker host):
  python3 remote_query.py \
      --index-prefix /mnt/music/home/joe/imageindex \
      --text "a yellow car" \
      --top-k 10 \
      --results-dir /mnt/music/home/joe/image_results
"""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import List, Tuple

import numpy as np
import polars as pl
from PIL import Image

import faiss
from sentence_transformers import SentenceTransformer


# --------- Config defaults --------- #

DEFAULT_MODEL_NAME = "clip-ViT-B-32"
DEFAULT_TOP_K = 10
DEFAULT_RESULTS_DIR = "/mnt/music/home/joe/image_results"


# --------- Utility functions --------- #


def load_metadata(meta_path: Path) -> dict:
    with meta_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def log(msg: str) -> None:
    """Log message with timestamp."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [Query] {msg}", flush=True)


def copy_result_image(src_path: Path, results_dir: Path, rank: int, timestamp: str) -> Path:
    """Copy image to results directory with timestamped name."""
    # Get file extension
    ext = src_path.suffix.lower()

    # Create new filename: match_YYYYMMDD_HHMMSS_rank001.jpg
    new_name = f"match_{timestamp}_rank{rank:03d}{ext}"
    dest_path = results_dir / new_name

    try:
        shutil.copy2(src_path, dest_path)
        return dest_path
    except Exception as e:
        log(f"WARNING: Failed to copy {src_path}: {e}")
        return None


# --------- Query Logic --------- #


def cmd_query(args: argparse.Namespace) -> None:
    query_start = time.time()

    prefix = Path(args.index_prefix).expanduser().resolve()
    results_dir = Path(args.results_dir).expanduser().resolve()

    parquet_path = prefix.with_suffix(".parquet")
    faiss_path = prefix.with_suffix(".faiss")
    meta_path = prefix.with_suffix(".meta.json")

    log(f"Query: {args.text!r}")
    log(f"Index prefix: {prefix}")
    log(f"Results directory: {results_dir}")

    # Validate index files exist
    if (
        not parquet_path.is_file()
        or not faiss_path.is_file()
        or not meta_path.is_file()
    ):
        log(
            f"ERROR: index files not found for prefix {prefix}.\n"
            f"Expected: {parquet_path}, {faiss_path}, {meta_path}"
        )
        sys.exit(1)

    # Load metadata
    log("Loading metadata...")
    meta = load_metadata(meta_path)
    model_name = meta.get("model_name", DEFAULT_MODEL_NAME)
    dim = int(meta.get("embedding_dim"))
    log(f"  Model: {model_name}")
    log(f"  Embedding dim: {dim}")
    log(f"  Total images: {meta.get('num_images')}")

    # Load table
    log("Loading Parquet index...")
    df = pl.read_parquet(parquet_path)
    paths = df["path"].to_list()
    emb_list = df["embedding"].to_list()
    embeddings = np.array(emb_list, dtype="float32")

    if embeddings.shape[1] != dim:
        log(
            f"ERROR: embedding dimension mismatch: meta says {dim}, "
            f"but Parquet has {embeddings.shape[1]}"
        )
        sys.exit(1)
    log(f"  Loaded {len(paths)} image paths and embeddings")

    # Load Faiss index
    log("Loading Faiss index...")
    index = faiss.read_index(str(faiss_path))

    if index.d != dim:
        log(
            f"ERROR: Faiss index dimension mismatch: index.d={index.d}, meta.dim={dim}"
        )
        sys.exit(1)
    log(f"  Index contains {index.ntotal} vectors")

    # Load model (CPU)
    log(f"Loading CLIP model: {model_name}...")
    model = SentenceTransformer(model_name, device="cpu")

    # Encode query
    query_text = args.text
    log(f"Encoding query text...")
    q_emb = model.encode(
        query_text,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype("float32")

    # Ensure shape (1, dim)
    q_emb = q_emb.reshape(1, -1)

    # Search
    top_k = args.top_k
    log(f"Searching for top-{top_k} matches...")
    scores, indices = index.search(q_emb, top_k)

    # Display results
    log("\nSearch Results:")
    log("-" * 80)

    results: List[Tuple[int, float, str]] = []

    for rank, (score, idx) in enumerate(zip(scores[0], indices[0]), start=1):
        if idx < 0 or idx >= len(paths):
            continue
        img_path = paths[idx]
        results.append((rank, score, img_path))
        log(f"  {rank:2d}. score={score:.4f}  {img_path}")

    # Copy results to results directory
    if args.copy_results and results:
        log("\n" + "-" * 80)
        log("Copying matching images to results directory...")

        # Create results directory
        results_dir.mkdir(parents=True, exist_ok=True)

        # Generate timestamp for this query
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        copied_count = 0
        failed_count = 0

        for rank, score, img_path in results:
            src_path = Path(img_path)

            if not src_path.exists():
                log(f"  WARNING: Source image not found: {src_path}")
                failed_count += 1
                continue

            dest_path = copy_result_image(src_path, results_dir, rank, timestamp)

            if dest_path:
                log(f"  Copied rank {rank}: {dest_path.name}")
                copied_count += 1
            else:
                failed_count += 1

        log("-" * 80)
        log(f"Results copied: {copied_count} succeeded, {failed_count} failed")
        log(f"Results directory: {results_dir}")

    # Summary
    total_time = time.time() - query_start
    log("-" * 80)
    log(f"Query completed in {total_time:.2f} seconds")


# --------- Main CLI --------- #


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Remote CLIP-based image search query (runs on worker host)."
    )

    p.add_argument(
        "--index-prefix",
        required=True,
        help="Prefix for index files (e.g., /mnt/music/home/joe/imageindex).",
    )
    p.add_argument(
        "--text",
        required=True,
        help="Text query, e.g. 'a yellow car' or 'sunset over mountains'.",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Number of results to return (default: {DEFAULT_TOP_K}).",
    )
    p.add_argument(
        "--results-dir",
        default=DEFAULT_RESULTS_DIR,
        help=f"Directory to copy matching images (default: {DEFAULT_RESULTS_DIR}).",
    )
    p.add_argument(
        "--copy-results",
        action="store_true",
        default=True,
        help="Copy matching images to results directory (default: True).",
    )
    p.add_argument(
        "--no-copy-results",
        action="store_false",
        dest="copy_results",
        help="Don't copy matching images, just display results.",
    )

    return p


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    cmd_query(args)


if __name__ == "__main__":
    main()
