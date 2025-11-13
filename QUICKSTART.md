# Quick Start Guide - Distributed Image Indexing

## TL;DR

```bash
# 1. Test system
./test_system.sh

# 2. Setup workers (first time only)
./setup_workers.sh

# 3. Run distributed indexing
python3 controller.py \
    --image-dir /Volumes/home/joe/images \
    --index-prefix /Volumes/home/joe/imageindex

# 4. Query the index (runs on remote worker)
python3 query_client.py \
    --text "sunset over mountains" \
    --top-k 10

# Results will be copied to /Volumes/home/joe/image_results
```

## What Gets Created

After successful indexing, you'll have:

```
/Volumes/home/joe/imageindex/
├── worker_0.parquet         # Partial index from worker 0
├── worker_0.faiss
├── worker_0.meta.json
├── worker_1.parquet         # Partial index from worker 1
├── worker_1.faiss
├── worker_1.meta.json
├── worker_2.parquet         # Partial index from worker 2
├── worker_2.faiss
├── worker_2.meta.json
├── worker_3.parquet         # Partial index from worker 3
├── worker_3.faiss
├── worker_3.meta.json
├── imageindex.parquet       # FINAL merged index (use this)
├── imageindex.faiss
└── imageindex.meta.json
```

**Use the merged files (without worker_ prefix) for queries.**

## Work Distribution

| Worker | Host | Images | RAM | Batch Size |
|--------|------|--------|-----|------------|
| Worker 0 | duc212-100g | 20% | 15GB | 8 |
| Worker 1 | duc213-100g | 20% | 15GB | 8 |
| Worker 2 | duc214-100g | 20% | 15GB | 8 |
| Worker 3 | duc17-40g   | 40% | 62GB | 32 |

## Expected Performance

- **4 workers parallel**: ~70-100 images/second
- **10,000 images**: ~2-3 minutes
- **100,000 images**: ~20-30 minutes
- **1,000,000 images**: ~3-5 hours

## Troubleshooting Quick Fixes

### Worker out of memory
```python
# Edit controller.py, reduce batch_size:
"duc212-100g.eng.qumulo.com": {"weight": 0.20, "batch_size": 4, "ram_gb": 15},
```

### SSH connection refused
```bash
# Test connection:
ssh root@duc212-100g.eng.qumulo.com "echo OK"
```

### NFS mount not found
```bash
# On worker:
ssh root@duc212-100g.eng.qumulo.com "ls /mnt/music/home/joe"

# On Mac:
ls /Volumes/home/joe
```

### Re-run failed worker manually
```bash
ssh root@duc212-100g.eng.qumulo.com "
cd /root/image_detection && \
python3 worker_index.py \
  --image-list worker_0_images.txt \
  --index-prefix /mnt/music/home/joe/imageindex/worker_0 \
  --worker-id 0 \
  --batch-size 8
"
```

### Merge partial indexes manually
```bash
python3 merge_indexes.py \
    --index-prefix /Volumes/home/joe/imageindex \
    --num-workers 4
```

## File Descriptions

| File | Purpose | Runs On |
|------|---------|---------|
| `controller.py` | Orchestrates indexing | Mac |
| `worker_index.py` | Processes images | Linux workers |
| `merge_indexes.py` | Merges partial indexes | Mac |
| `query_client.py` | **Submit queries from Mac** | **Mac** |
| `remote_query.py` | **Executes queries & copies results** | **Linux workers** |
| `setup_workers.sh` | Installs dependencies | Mac (via SSH) |
| `test_system.sh` | Tests connectivity | Mac |
| ~~`images_search.py`~~ | ~~Original script~~ | ~~Not used~~ |

## Common Commands

### Check worker status
```bash
# Is worker still running?
ssh root@duc212-100g.eng.qumulo.com "ps aux | grep worker_index.py"

# Check memory usage
ssh root@duc212-100g.eng.qumulo.com "free -h"

# Check CPU usage
ssh root@duc212-100g.eng.qumulo.com "top -bn1 | head -20"
```

### Monitor index progress
```bash
# Check partial index files
watch -n 5 'ls -lh /Volumes/home/joe/imageindex/worker_*.parquet'

# Count completed images per worker
ssh root@duc212-100g.eng.qumulo.com "wc -l /root/image_detection/worker_0_images.txt"
```

### Clean up after run
```bash
# Remove worker temp files (on each worker)
for host in $(cat hosts); do
    ssh root@$host "rm -rf /root/image_detection/work_*"
done

# Remove local work directory
rm -rf work_*
```

## Query Examples

All queries run on remote workers (no local Python dependencies needed except standard library):

```bash
# Find images of cars (copied to /Volumes/home/joe/image_results/match_TIMESTAMP_rank001.jpg)
python3 query_client.py \
    --text "a red sports car" \
    --top-k 5

# Find landscapes
python3 query_client.py \
    --text "mountain landscape with lake" \
    --top-k 10

# Find people
python3 query_client.py \
    --text "person smiling" \
    --top-k 20

# Use specific worker (default is duc17-40g)
python3 query_client.py \
    --text "sunset" \
    --worker duc212-100g.eng.qumulo.com

# Just display results, don't copy images
python3 query_client.py \
    --text "cat" \
    --no-copy-results
```

### Result Files

Matching images are copied to `/Volumes/home/joe/image_results/` with names like:
- `match_20250113_143022_rank001.jpg` (best match)
- `match_20250113_143022_rank002.jpg` (2nd best)
- `match_20250113_143022_rank003.jpg` (3rd best)

The timestamp format is: `YYYYMMDD_HHMMSS`

## Tips

1. **First run is slower**: Workers download CLIP model (~350MB) once
2. **Watch RAM**: If workers crash, reduce batch_size
3. **Use tmux/screen**: For long-running jobs on Mac
4. **Test small first**: Try with 100 images before full run
5. **Check NFS speed**: Slow NFS = slow indexing

## Getting Help

See `README_DISTRIBUTED.md` for full documentation.
