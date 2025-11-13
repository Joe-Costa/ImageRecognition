#!/usr/bin/env python3
"""
Query client - runs on Mac to submit queries to remote workers.

This script sends queries to a remote worker host, which performs the search
and copies matching images to the results directory. Results can then be
accessed via the SMB mount on Mac.

Usage (on Mac):
  python3 query_client.py \
      --text "a yellow car" \
      --top-k 10 \
      --worker duc17-40g.eng.qumulo.com
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


# --------- Config --------- #

DEFAULT_WORKER = "duc17-40g.eng.qumulo.com"  # Use the high-RAM worker for queries
REMOTE_INDEX_PREFIX = "/mnt/music/home/joe/imageindex"
REMOTE_RESULTS_DIR = "/mnt/music/home/joe/image_results"
REMOTE_SCRIPT_PATH = "/root/image_detection/remote_query.py"
LOCAL_RESULTS_DIR = "/Volumes/home/joe/image_results"


# --------- Utility functions --------- #


def log(msg: str) -> None:
    """Log message with timestamp."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [Client] {msg}", flush=True)


def ssh_exec(host: str, command: str, capture_output: bool = False) -> subprocess.CompletedProcess:
    """Execute command on remote host via SSH."""
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        f"root@{host}",
        command
    ]

    if capture_output:
        return subprocess.run(ssh_cmd, capture_output=True, text=True)
    else:
        # Stream output in real-time
        return subprocess.run(ssh_cmd)


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


def check_remote_script(host: str, script_path: str) -> bool:
    """Check if remote query script exists on worker."""
    result = ssh_exec(host, f"test -f {script_path} && echo 'OK'", capture_output=True)
    return "OK" in result.stdout


def deploy_remote_script(host: str) -> bool:
    """Deploy remote_query.py to worker if not present."""
    local_script = Path(__file__).parent / "remote_query.py"

    if not local_script.exists():
        log(f"ERROR: Local script not found: {local_script}")
        return False

    log(f"Deploying remote_query.py to {host}...")

    # Create remote directory
    ssh_exec(host, "mkdir -p /root/image_detection", capture_output=True)

    # Copy script
    if not scp_file(local_script, host, REMOTE_SCRIPT_PATH):
        return False

    # Make executable
    ssh_exec(host, f"chmod +x {REMOTE_SCRIPT_PATH}", capture_output=True)

    log("Script deployed successfully")
    return True


# --------- Query Client Logic --------- #


def cmd_query_client(args: argparse.Namespace) -> None:
    start_time = time.time()

    worker = args.worker
    query_text = args.text
    top_k = args.top_k

    log(f"Query: {query_text!r}")
    log(f"Worker: {worker}")
    log(f"Top-K: {top_k}")

    # Check SSH connectivity
    log("Testing SSH connection...")
    result = ssh_exec(worker, "echo 'OK'", capture_output=True)
    if result.returncode != 0 or "OK" not in result.stdout:
        log(f"ERROR: Cannot connect to {worker}")
        sys.exit(1)
    log("SSH connection OK")

    # Check if remote script exists, deploy if needed
    if not check_remote_script(worker, REMOTE_SCRIPT_PATH):
        log("Remote query script not found on worker")
        if not deploy_remote_script(worker):
            log("ERROR: Failed to deploy remote script")
            sys.exit(1)

    # Build remote command
    copy_flag = "--copy-results" if args.copy_results else "--no-copy-results"

    remote_cmd = (
        f"cd /root/image_detection && "
        f"python3 remote_query.py "
        f"--index-prefix {REMOTE_INDEX_PREFIX} "
        f"--text '{query_text}' "
        f"--top-k {top_k} "
        f"--results-dir {REMOTE_RESULTS_DIR} "
        f"{copy_flag}"
    )

    log(f"\nExecuting query on {worker}...")
    log("-" * 80)

    # Execute query on remote worker (stream output)
    result = ssh_exec(worker, remote_cmd)

    log("-" * 80)

    if result.returncode != 0:
        log(f"ERROR: Query failed on worker (exit code: {result.returncode})")
        sys.exit(1)

    # Check results locally if copy was enabled
    if args.copy_results:
        log("\nChecking local results directory...")
        local_results = Path(LOCAL_RESULTS_DIR)

        if not local_results.exists():
            log(f"WARNING: Results directory not found locally: {local_results}")
            log("Make sure SMB mount is active: /Volumes/home/joe")
        else:
            # Find results from this query (last minute)
            recent_files = []
            cutoff_time = time.time() - 120  # Last 2 minutes

            try:
                for f in local_results.glob("match_*.jpg"):
                    if f.stat().st_mtime > cutoff_time:
                        recent_files.append(f)

                for f in local_results.glob("match_*.png"):
                    if f.stat().st_mtime > cutoff_time:
                        recent_files.append(f)

                if recent_files:
                    log(f"\nFound {len(recent_files)} result image(s) at:")
                    log(f"  {local_results}")
                    log("\nRecent files:")
                    for f in sorted(recent_files, key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
                        log(f"  {f.name}")
                else:
                    log("\nNo recent result files found (may take a moment to sync)")
            except Exception as e:
                log(f"WARNING: Could not check results directory: {e}")

    total_time = time.time() - start_time
    log(f"\nTotal query time: {total_time:.2f} seconds")


# --------- Main CLI --------- #


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Query client for remote CLIP-based image search (runs on Mac)."
    )

    p.add_argument(
        "--text",
        required=True,
        help="Text query, e.g. 'a yellow car' or 'sunset over mountains'.",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of results to return (default: 10).",
    )
    p.add_argument(
        "--worker",
        default=DEFAULT_WORKER,
        help=f"Worker host to run query on (default: {DEFAULT_WORKER}).",
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
    cmd_query_client(args)


if __name__ == "__main__":
    main()
