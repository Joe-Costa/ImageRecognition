#!/usr/bin/env python3
"""
Controller script for distributed image indexing.

This script orchestrates the distributed processing of images across multiple
worker hosts. It handles work distribution, worker execution, monitoring,
and final index merging.

Usage:
  python controller.py \
      --image-dir /Volumes/files/home/joe/images \
      --index-prefix /Volumes/files/home/joe/imageindex \
      --hosts-file ./hosts \
      --workers-script ./worker_index.py
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Dict, Tuple

# --------- Config --------- #

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"}

# Worker configuration with RAM-based weighting
# Using clip-ViT-L-14-336 (best quality, 768-dim, processes 336x336 images)
WORKER_CONFIG = {
    "duc212-100g.eng.qumulo.com": {"weight": 0.20, "batch_size": 2, "ram_gb": 15, "model": "clip-ViT-L-14-336"},
    "duc213-100g.eng.qumulo.com": {"weight": 0.20, "batch_size": 2, "ram_gb": 15, "model": "clip-ViT-L-14-336"},
    "duc214-100g.eng.qumulo.com": {"weight": 0.20, "batch_size": 2, "ram_gb": 15, "model": "clip-ViT-L-14-336"},
    "duc17-40g.eng.qumulo.com": {"weight": 0.40, "batch_size": 10, "ram_gb": 62, "model": "clip-ViT-L-14-336"},
}

REMOTE_WORK_DIR = "/root/ImageRecognition"
REMOTE_IMAGE_DIR = "/mnt/music/home/joe/images"
REMOTE_INDEX_PREFIX = "/mnt/music/home/joe/imageindex"


# --------- Utility functions --------- #


def log(msg: str) -> None:
    """Log message with timestamp."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [Controller] {msg}", flush=True)


def find_images(root: Path) -> List[Path]:
    """Recursively find image files under root with known extensions."""
    log(f"Scanning for images in: {root}")
    images: List[Path] = []
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            ext = Path(name).suffix.lower()
            if ext in VALID_EXTENSIONS:
                images.append(Path(dirpath) / name)
    log(f"Found {len(images)} images")
    return images


def translate_path_to_remote(local_path: Path, local_base: Path, remote_base: str) -> str:
    """Translate local Mac path to remote Linux NFS path."""
    # Get relative path from local base
    rel_path = local_path.relative_to(local_base)
    # Construct remote path
    remote_path = Path(remote_base) / rel_path
    return str(remote_path)


def split_work(images: List[Path], weights: List[float]) -> List[List[Path]]:
    """Split images into chunks based on weights."""
    total = len(images)
    chunks = []
    start = 0

    for i, weight in enumerate(weights):
        if i == len(weights) - 1:
            # Last chunk gets all remaining images
            chunk = images[start:]
        else:
            chunk_size = int(total * weight)
            chunk = images[start:start + chunk_size]
            start += chunk_size
        chunks.append(chunk)

    return chunks


def load_hosts(hosts_file: Path) -> List[str]:
    """Load host list from file."""
    with hosts_file.open("r") as f:
        hosts = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return hosts


def ssh_exec(host: str, command: str, background: bool = False) -> subprocess.Popen:
    """Execute command on remote host via SSH."""
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", f"root@{host}", command]

    if background:
        # Run in background, return process handle
        proc = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return proc
    else:
        # Run synchronously
        result = subprocess.run(ssh_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log(f"ERROR: SSH command failed on {host}: {result.stderr}")
        return result


def scp_file(local_path: Path, host: str, remote_path: str) -> bool:
    """Copy file to remote host via SCP."""
    scp_cmd = [
        "scp",
        "-o", "StrictHostKeyChecking=no",
        str(local_path),
        f"root@{host}:{remote_path}"
    ]
    result = subprocess.run(scp_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"ERROR: SCP failed to {host}: {result.stderr}")
        return False
    return True


def check_worker_prerequisites(host: str) -> bool:
    """Check if worker has required setup."""
    log(f"Checking prerequisites on {host}...")

    # Check NFS mount
    result = ssh_exec(host, "test -d /mnt/music/home/joe && echo 'OK' || echo 'FAIL'")
    if "OK" not in result.stdout:
        log(f"ERROR: NFS mount not accessible on {host}")
        return False

    # Check Python
    result = ssh_exec(host, "python3 --version")
    if result.returncode != 0:
        log(f"ERROR: Python3 not found on {host}")
        return False

    log(f"Prerequisites OK on {host}")
    return True


# --------- Main Controller Logic --------- #


def cmd_controller(args: argparse.Namespace) -> None:
    start_time = time.time()

    # Validate inputs
    image_dir = Path(args.image_dir).expanduser().resolve()
    index_prefix_local = Path(args.index_prefix).expanduser().resolve()
    hosts_file = Path(args.hosts_file).expanduser().resolve()
    worker_script = Path(args.workers_script).expanduser().resolve()

    if not image_dir.is_dir():
        log(f"ERROR: Image directory not found: {image_dir}")
        sys.exit(1)

    if not hosts_file.is_file():
        log(f"ERROR: Hosts file not found: {hosts_file}")
        sys.exit(1)

    if not worker_script.is_file():
        log(f"ERROR: Worker script not found: {worker_script}")
        sys.exit(1)

    # Load hosts
    hosts = load_hosts(hosts_file)
    log(f"Loaded {len(hosts)} worker hosts")

    # Validate hosts are in WORKER_CONFIG
    for host in hosts:
        if host not in WORKER_CONFIG:
            log(f"ERROR: Host {host} not in WORKER_CONFIG")
            sys.exit(1)

    # Check prerequisites on all hosts
    if not args.skip_checks:
        for host in hosts:
            if not check_worker_prerequisites(host):
                sys.exit(1)

    # Find all images
    images = find_images(image_dir)
    if not images:
        log("ERROR: No images found")
        sys.exit(1)

    # Translate paths to remote format
    remote_images = [
        translate_path_to_remote(img, image_dir, REMOTE_IMAGE_DIR)
        for img in images
    ]

    # Split work based on weights
    weights = [WORKER_CONFIG[host]["weight"] for host in hosts]
    work_chunks = split_work(remote_images, weights)

    log("Work distribution:")
    for i, (host, chunk) in enumerate(zip(hosts, work_chunks)):
        log(f"  Worker {i} ({host}): {len(chunk)} images ({100*len(chunk)/len(images):.1f}%)")

    # Create work directory on local machine
    work_dir = Path(f"./work_{int(time.time())}")
    work_dir.mkdir(exist_ok=True)
    log(f"Created local work directory: {work_dir}")

    # Prepare and deploy work to each host
    worker_processes: List[Tuple[str, int, subprocess.Popen]] = []

    for worker_id, (host, chunk) in enumerate(zip(hosts, work_chunks)):
        log(f"Preparing worker {worker_id} on {host}...")

        # Create image list file
        list_file = work_dir / f"worker_{worker_id}_images.txt"
        with list_file.open("w") as f:
            for img_path in chunk:
                f.write(f"{img_path}\n")

        log(f"  Created image list: {list_file} ({len(chunk)} images)")

        # Create remote work directory
        ssh_exec(host, f"mkdir -p {REMOTE_WORK_DIR}")

        # Copy worker script
        remote_script = f"{REMOTE_WORK_DIR}/worker_index.py"
        if not scp_file(worker_script, host, remote_script):
            log(f"ERROR: Failed to copy worker script to {host}")
            sys.exit(1)
        ssh_exec(host, f"chmod +x {remote_script}")

        # Copy image list
        remote_list = f"{REMOTE_WORK_DIR}/worker_{worker_id}_images.txt"
        if not scp_file(list_file, host, remote_list):
            log(f"ERROR: Failed to copy image list to {host}")
            sys.exit(1)

        # Prepare worker command
        batch_size = WORKER_CONFIG[host]["batch_size"]
        model_name = WORKER_CONFIG[host].get("model", "clip-ViT-B-32")
        remote_index_prefix = f"{REMOTE_INDEX_PREFIX}/worker_{worker_id}"

        worker_cmd = (
            f"cd {REMOTE_WORK_DIR} && "
            f"venv/bin/python worker_index.py "
            f"--image-list {remote_list} "
            f"--index-prefix {remote_index_prefix} "
            f"--worker-id {worker_id} "
            f"--batch-size {batch_size} "
            f"--model-name {model_name}"
        )

        log(f"  Starting worker {worker_id} on {host}...")
        log(f"  Command: {worker_cmd}")

        # Execute worker in background
        proc = ssh_exec(host, worker_cmd, background=True)
        worker_processes.append((host, worker_id, proc))

        log(f"  Worker {worker_id} started (PID: {proc.pid})")

    # Monitor workers
    log(f"\nMonitoring {len(worker_processes)} workers...")
    log("(This may take a while depending on the number of images)\n")

    completed = []
    failed = []

    while worker_processes:
        time.sleep(10)  # Check every 10 seconds

        for host, worker_id, proc in worker_processes[:]:
            retcode = proc.poll()

            if retcode is not None:
                # Worker finished
                worker_processes.remove((host, worker_id, proc))

                if retcode == 0:
                    log(f"Worker {worker_id} ({host}) completed successfully")
                    completed.append((host, worker_id))
                else:
                    stdout, stderr = proc.communicate()
                    log(f"Worker {worker_id} ({host}) FAILED (exit code: {retcode})")
                    log(f"  STDERR: {stderr}")
                    failed.append((host, worker_id))

    # Summary
    total_time = time.time() - start_time
    log(f"\n{'='*60}")
    log(f"All workers finished in {total_time/60:.1f} minutes")
    log(f"  Completed: {len(completed)}")
    log(f"  Failed: {len(failed)}")

    if failed:
        log("\nFailed workers:")
        for host, worker_id in failed:
            log(f"  Worker {worker_id} on {host}")
        sys.exit(1)

    # Now merge indexes using remote merge client
    log(f"\nStarting index merge on remote worker...")

    # Use merge_client.py to run merge on a worker (no local ML dependencies needed)
    merge_client = Path(__file__).parent / "merge_client.py"
    if not merge_client.exists():
        log("ERROR: merge_client.py not found")
        sys.exit(1)

    merge_cmd = [
        "python3",
        str(merge_client),
        "--num-workers", str(len(hosts))
    ]

    log(f"Running: {' '.join(merge_cmd)}")
    result = subprocess.run(merge_cmd)

    if result.returncode != 0:
        log("ERROR: Index merge failed")
        sys.exit(1)

    log("\n" + "="*60)
    log("DISTRIBUTED INDEXING COMPLETE!")
    log(f"Total time: {(time.time() - start_time)/60:.1f} minutes")
    log(f"Index files written to: {index_prefix_local}")
    log("="*60)


# --------- Main CLI --------- #


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Controller for distributed CLIP-based image indexing."
    )

    p.add_argument(
        "--image-dir",
        required=True,
        help="Local directory containing images (e.g., /Volumes/files/home/joe/images).",
    )
    p.add_argument(
        "--index-prefix",
        required=True,
        help="Local prefix for final index files (e.g., /Volumes/files/home/joe/imageindex).",
    )
    p.add_argument(
        "--hosts-file",
        default="./hosts",
        help="File containing worker hostnames (default: ./hosts).",
    )
    p.add_argument(
        "--workers-script",
        default="./worker_index.py",
        help="Path to worker script (default: ./worker_index.py).",
    )
    p.add_argument(
        "--skip-checks",
        action="store_true",
        help="Skip prerequisite checks on workers.",
    )

    return p


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    cmd_controller(args)


if __name__ == "__main__":
    main()
