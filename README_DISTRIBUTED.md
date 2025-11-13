# Distributed Image Indexing System

A distributed system for processing large image collections using CLIP (via sentence-transformers) across multiple Linux worker hosts, controlled from a Mac.

## System Overview

### Architecture

```
Mac Controller (this machine)
    |
    | SSH + Work Distribution
    |
    +-- Worker 1 (duc212): 20% of images, 15GB RAM, batch_size=8
    +-- Worker 2 (duc213): 20% of images, 15GB RAM, batch_size=8
    +-- Worker 3 (duc214): 20% of images, 15GB RAM, batch_size=8
    +-- Worker 4 (duc17):  40% of images, 62GB RAM, batch_size=32
    |
    | Partial indexes written to NFS
    |
Controller merges partial indexes --> Unified index
```

### Components

- **controller.py**: Orchestrates the entire process (runs on Mac)
- **worker_index.py**: Processes image batches (runs on Linux workers)
- **merge_indexes.py**: Merges partial indexes into final index (runs on Mac)
- **setup_workers.sh**: Sets up dependencies on all workers
- **hosts**: List of worker hostnames

## Prerequisites

### On Mac (Controller)
- Python 3.8+
- SSH access to all workers as `root`
- SMB mount: `/Volumes/home/joe` → `/mnt/music/home/joe` (NFS on workers)

### On Workers
- Ubuntu 24.04
- Python 3.12.3
- NFS mount: `/mnt/music/home/joe` accessible
- SSH key-based authentication for `root` user
- Project directory at `/root/image_detection`

## Setup

### 1. Install Dependencies on Mac

```bash
cd /Users/joe/Python_Projects/ImageRecognition
pip install -r requirements.txt
```

### 2. Setup Workers

Run the setup script to install dependencies on all workers:

```bash
./setup_workers.sh
```

This will:
- Check SSH connectivity
- Verify NFS mounts
- Install Python packages (sentence-transformers, faiss-cpu, polars, pillow, numpy)
- Create working directories
- Verify installations

### 3. Verify Setup

The setup script will show a summary. All workers should report success.

## Usage

### Step 1: Run Distributed Indexing

```bash
python3 controller.py \
    --image-dir /Volumes/home/joe/images \
    --index-prefix /Volumes/home/joe/imageindex
```

**What happens:**
1. Controller scans for images in `/Volumes/home/joe/images`
2. Splits work: 40% to duc17, 20% each to duc212/213/214
3. Deploys image lists to workers via SCP
4. Launches worker processes via SSH (parallel execution)
5. Monitors worker progress
6. Merges partial indexes when all workers complete
7. Creates final unified index

**Output files:**
```
/Volumes/home/joe/imageindex.parquet      # Paths + embeddings
/Volumes/home/joe/imageindex.faiss        # Vector index
/Volumes/home/joe/imageindex.meta.json    # Metadata
```

### Step 2: Query the Index

Use the query client (queries run on remote workers, no local ML dependencies needed):

```bash
python3 query_client.py \
    --text "a yellow car" \
    --top-k 10
```

**What happens:**
1. Query client connects to worker via SSH (default: duc17-40g)
2. Deploys `remote_query.py` if not present
3. Worker loads index and CLIP model
4. Worker performs semantic search
5. Worker copies matching images to `/mnt/music/home/joe/image_results`
6. Images renamed as `match_YYYYMMDD_HHMMSS_rank001.jpg`
7. Results accessible on Mac at `/Volumes/home/joe/image_results`

**Query options:**
```bash
# Use specific worker
python3 query_client.py --text "sunset" --worker duc212-100g.eng.qumulo.com

# Just show results without copying images
python3 query_client.py --text "car" --no-copy-results

# More results
python3 query_client.py --text "landscape" --top-k 20
```

## Configuration

### Worker Configuration

Edit `controller.py` to adjust worker settings:

```python
WORKER_CONFIG = {
    "duc212-100g.eng.qumulo.com": {"weight": 0.20, "batch_size": 8, "ram_gb": 15},
    "duc213-100g.eng.qumulo.com": {"weight": 0.20, "batch_size": 8, "ram_gb": 15},
    "duc214-100g.eng.qumulo.com": {"weight": 0.20, "batch_size": 8, "ram_gb": 15},
    "duc17-40g.eng.qumulo.com": {"weight": 0.40, "batch_size": 32, "ram_gb": 62},
}
```

- **weight**: Fraction of total work (must sum to 1.0)
- **batch_size**: Images per batch (lower for less RAM)
- **ram_gb**: Available RAM (for reference)

### Paths

Edit these constants in `controller.py` if needed:

```python
REMOTE_WORK_DIR = "/root/image_detection"        # Worker project directory
REMOTE_IMAGE_DIR = "/mnt/music/home/joe/images"  # NFS image path
REMOTE_INDEX_PREFIX = "/mnt/music/home/joe/imageindex"  # NFS index path
```

## Monitoring

### During Execution

The controller shows real-time progress:
```
[2025-01-13 10:30:15] [Controller] Starting worker 0 on duc212-100g.eng.qumulo.com...
[2025-01-13 10:30:15] [Controller] Worker 0 started (PID: 12345)
[2025-01-13 10:30:25] [Controller] Monitoring 4 workers...
```

Workers log to stdout (visible in controller):
```
[2025-01-13 10:30:20] [Worker 0] Encoding images in batches of 8...
[2025-01-13 10:30:30] [Worker 0] Progress: 100/500 images (20.0%) - 10.5 img/s - ETA: 0.6min
```

### Manual Monitoring

Check worker progress via SSH:
```bash
# Check if worker is running
ssh root@duc212-100g.eng.qumulo.com "ps aux | grep worker_index.py"

# Monitor memory usage
ssh root@duc212-100g.eng.qumulo.com "free -h"

# Check worker logs (if redirected)
ssh root@duc212-100g.eng.qumulo.com "tail -f /root/image_detection/worker_0.log"
```

## Troubleshooting

### Worker Fails with OOM (Out of Memory)

Reduce batch size in `WORKER_CONFIG`:
```python
"duc212-100g.eng.qumulo.com": {"weight": 0.20, "batch_size": 4, "ram_gb": 15},
```

### SSH Connection Fails

Verify SSH keys:
```bash
ssh root@duc212-100g.eng.qumulo.com "echo 'OK'"
```

### NFS Mount Not Accessible

Check mount on worker:
```bash
ssh root@duc212-100g.eng.qumulo.com "ls /mnt/music/home/joe/images"
```

Check mount on Mac:
```bash
ls /Volumes/home/joe/images
```

### Worker Hangs During Model Download

First run may download CLIP model (~350MB). This happens once per worker.

Check download progress:
```bash
ssh root@duc212-100g.eng.qumulo.com "ls -lh ~/.cache/torch/sentence_transformers/"
```

### Partial Index Merge Fails

Verify all worker outputs exist:
```bash
ls -lh /Volumes/home/joe/imageindex/worker_*.{parquet,faiss,meta.json}
```

### Re-run After Failure

If a worker fails, you can:
1. Fix the issue (RAM, network, etc.)
2. Re-run controller.py (it will recreate work chunks)

Or manually re-run a single worker:
```bash
ssh root@duc212-100g.eng.qumulo.com "cd /root/image_detection && \
  python3 worker_index.py \
    --image-list worker_0_images.txt \
    --index-prefix /mnt/music/home/joe/imageindex/worker_0 \
    --worker-id 0 \
    --batch-size 8"
```

## Performance

### Expected Throughput

- **Single worker (15GB RAM, batch_size=8)**: ~10-15 images/sec
- **duc17 (62GB RAM, batch_size=32)**: ~30-40 images/sec
- **Total (4 workers)**: ~70-100 images/sec

### Bottlenecks

1. **CPU**: CLIP encoding is CPU-intensive (no GPU)
2. **RAM**: Limits batch size and model loading
3. **Network**: NFS reads for images (usually not bottleneck)

### Optimization Tips

1. **Increase batch size** on workers with more RAM
2. **Add more workers** (modify hosts file and WORKER_CONFIG)
3. **Use faster CPUs** if available
4. **Reduce image resolution** before indexing (if acceptable)

## File Structure

```
ImageRecognition/
├── images_search.py          # Original single-machine script
├── controller.py             # NEW: Mac orchestration script
├── worker_index.py           # NEW: Linux worker script
├── merge_indexes.py          # NEW: Index merging utility
├── setup_workers.sh          # NEW: Deployment script
├── requirements.txt          # Python dependencies
├── hosts                     # Worker hostnames
└── README_DISTRIBUTED.md     # This file
```

## Advanced Usage

### Running Only Indexing (No Merge)

Comment out the merge section in `controller.py`:
```python
# log(f"\nStarting index merge...")
# merge_cmd = [...]
# subprocess.run(merge_cmd)
```

Then manually merge later:
```bash
python3 merge_indexes.py \
    --index-prefix /Volumes/home/joe/imageindex \
    --num-workers 4
```

### Custom Image List

Instead of scanning, provide a pre-generated list:
```bash
# Create image list
find /Volumes/home/joe/images -type f -name "*.jpg" > all_images.txt

# Modify controller.py to read from this file instead of scanning
```

### Testing with Small Dataset

Test with a subset first:
```bash
# Create test directory
mkdir -p /Volumes/home/joe/images_test
cp /Volumes/home/joe/images/*.jpg /Volumes/home/joe/images_test/ | head -100

# Run indexing on test set
python3 controller.py \
    --image-dir /Volumes/home/joe/images_test \
    --index-prefix /Volumes/home/joe/imageindex_test
```

## License

Same as original `images_search.py` script.
