#!/usr/bin/env python3
"""
Merge client - runs merge_indexes.py on a remote worker.

Usage:
  python3 merge_client.py \
      --index-prefix /Volumes/files/home/joe/imageindex \
      --num-workers 4
"""

import argparse
import subprocess
import sys
import time


# --------- Config --------- #

DEFAULT_WORKER = "duc17-40g.eng.qumulo.com"  # Use the high-RAM worker
REMOTE_INDEX_PREFIX = "/mnt/music/home/joe/imageindex"


# --------- Utility functions --------- #


def log(msg: str) -> None:
    """Log message with timestamp."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [MergeClient] {msg}", flush=True)


def ssh_exec(host: str, command: str) -> subprocess.CompletedProcess:
    """Execute command on remote host via SSH."""
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        f"root@{host}",
        command
    ]
    return subprocess.run(ssh_cmd)


# --------- Main Logic --------- #


def cmd_merge_client(args: argparse.Namespace) -> None:
    start_time = time.time()

    worker = args.worker
    num_workers = args.num_workers

    log(f"Merging {num_workers} worker indexes on {worker}...")

    # Check SSH connectivity
    log("Testing SSH connection...")
    result = ssh_exec(worker, "echo 'OK'")
    if result.returncode != 0:
        log(f"ERROR: Cannot connect to {worker}")
        sys.exit(1)
    log("SSH connection OK")

    # Build remote command
    remote_cmd = (
        f"cd /root/ImageRecognition && "
        f"venv/bin/python merge_indexes.py "
        f"--index-prefix {REMOTE_INDEX_PREFIX} "
        f"--num-workers {num_workers}"
    )

    log(f"\nExecuting merge on {worker}...")
    log("-" * 80)

    # Execute merge on remote worker
    result = ssh_exec(worker, remote_cmd)

    log("-" * 80)

    if result.returncode != 0:
        log(f"ERROR: Merge failed on worker (exit code: {result.returncode})")
        sys.exit(1)

    total_time = time.time() - start_time
    log(f"\nMerge completed in {total_time:.2f} seconds")
    log(f"Index files created at: {REMOTE_INDEX_PREFIX}")


# --------- Main CLI --------- #


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Client for merging indexes on remote worker (runs on Mac)."
    )

    p.add_argument(
        "--index-prefix",
        default="/Volumes/files/home/joe/imageindex",
        help="Local prefix for index files (will be translated to remote path).",
    )
    p.add_argument(
        "--num-workers",
        type=int,
        required=True,
        help="Number of workers that generated partial indexes.",
    )
    p.add_argument(
        "--worker",
        default=DEFAULT_WORKER,
        help=f"Worker host to run merge on (default: {DEFAULT_WORKER}).",
    )

    return p


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    cmd_merge_client(args)


if __name__ == "__main__":
    main()
