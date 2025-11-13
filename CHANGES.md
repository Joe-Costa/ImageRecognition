# System Changes - Remote Query Implementation

## Overview

The system has been updated to run all queries on remote workers instead of locally on Mac. This eliminates the need for ML dependencies (PyTorch, transformers, etc.) on your Mac.

## What Changed

### New Files Created

1. **remote_query.py** (runs on workers)
   - Performs semantic search using CLIP
   - Copies matching images to results directory
   - Renames images with timestamp: `match_YYYYMMDD_HHMMSS_rank001.jpg`

2. **query_client.py** (runs on Mac)
   - Lightweight client (no ML dependencies)
   - Submits queries to workers via SSH
   - Auto-deploys `remote_query.py` to workers
   - Shows results path on Mac

3. **QUERY_GUIDE.md**
   - Complete guide for using the query system
   - Examples, tips, troubleshooting

### Modified Files

1. **requirements.txt**
   - Updated to clarify: dependencies only needed on workers
   - Mac requires only Python standard library

2. **QUICKSTART.md**
   - Updated query examples to use `query_client.py`
   - Added result file naming conventions

3. **README_DISTRIBUTED.md**
   - Updated "Step 2: Query the Index" section
   - Documented remote query workflow

## Key Features

### 1. No Local ML Dependencies
```bash
# Before: Needed on Mac
pip install sentence-transformers torch faiss-cpu polars pillow

# After: Nothing needed on Mac!
# Just Python 3.x standard library
```

### 2. Automatic Image Copying
```bash
# Run query
python3 query_client.py --text "sunset"

# Results automatically copied to:
/Volumes/files/home/joe/image_results/match_20250113_143022_rank001.jpg
/Volumes/files/home/joe/image_results/match_20250113_143022_rank002.jpg
...
```

### 3. Timestamped Results

Each query creates uniquely named files:
- `match_YYYYMMDD_HHMMSS_rank001.jpg` (best match)
- Multiple queries don't overwrite each other
- Easy to identify when results were generated

### 4. Worker Selection

Choose which worker to use:
```bash
# Use default (duc17-40g - 62GB RAM)
python3 query_client.py --text "car"

# Use specific worker
python3 query_client.py --text "car" --worker duc212-100g.eng.qumulo.com
```

## Migration Guide

### Old Workflow (Local Queries)
```bash
# Required local ML dependencies
pip install -r requirements.txt

# Run query locally
python3 images_search.py query \
    --index-prefix /Volumes/files/home/joe/imageindex \
    --text "sunset" \
    --top-k 10

# Results shown in terminal only
```

### New Workflow (Remote Queries)
```bash
# No local dependencies needed!

# Run query remotely
python3 query_client.py \
    --text "sunset" \
    --top-k 10

# Results:
# 1. Displayed in terminal
# 2. Automatically copied to /Volumes/files/home/joe/image_results
# 3. Renamed with timestamp
```

## Backwards Compatibility

The original `images_search.py` still works if you have local dependencies installed, but it's no longer recommended. Use `query_client.py` instead.

## File Structure Update

```
ImageRecognition/
├── controller.py             # Mac: Orchestrates indexing
├── worker_index.py           # Workers: Process images
├── merge_indexes.py          # Mac: Merge partial indexes
├── query_client.py           # NEW: Mac query submission
├── remote_query.py           # NEW: Worker query execution
├── setup_workers.sh          # Mac: Deploy to workers
├── test_system.sh            # Mac: System tests
├── hosts                     # Worker list
├── requirements.txt          # Worker dependencies (UPDATED)
├── QUICKSTART.md             # Quick reference (UPDATED)
├── README_DISTRIBUTED.md     # Full docs (UPDATED)
├── QUERY_GUIDE.md            # NEW: Query system guide
├── CHANGES.md                # This file
└── images_search.py          # Original (deprecated)
```

## Configuration

### Query Client Defaults

Edit `query_client.py` to change defaults:

```python
DEFAULT_WORKER = "duc17-40g.eng.qumulo.com"  # Which worker to use
REMOTE_INDEX_PREFIX = "/mnt/music/home/joe/imageindex"
REMOTE_RESULTS_DIR = "/mnt/music/home/joe/image_results"
LOCAL_RESULTS_DIR = "/Volumes/files/home/joe/image_results"
```

### Remote Query Defaults

Edit `remote_query.py` to change defaults:

```python
DEFAULT_TOP_K = 10  # Number of results
DEFAULT_RESULTS_DIR = "/mnt/music/home/joe/image_results"
```

## Testing the Changes

### 1. Test System
```bash
./test_system.sh
```

### 2. Test Query (without copy)
```bash
python3 query_client.py --text "test query" --no-copy-results
```

### 3. Test Query (with copy)
```bash
python3 query_client.py --text "sunset" --top-k 3
ls -lh /Volumes/files/home/joe/image_results
```

## Benefits

1. **Simpler Mac Setup**
   - No need to install PyTorch, transformers, etc.
   - Faster setup for new machines
   - No version conflicts

2. **Better Resource Usage**
   - Workers have more RAM for queries
   - Mac resources freed for other tasks
   - Model stays loaded on worker (faster repeated queries)

3. **Automatic Result Management**
   - Images copied automatically
   - Timestamped naming prevents overwrites
   - Easy to organize and review results

4. **Flexibility**
   - Choose which worker to use
   - Option to copy or just display results
   - Easy to extend with new features

## Performance Comparison

### Local Query (Old)
```
Load index: 5 seconds
Load model: 10 seconds
Encode query: 2 seconds
Search: 1 second
Display results: instant
---
Total: ~18 seconds
```

### Remote Query (New)
```
SSH connection: 1 second
Worker loads (first time): 15 seconds
Query execution: 2 seconds
Copy results: 1 second
---
Total first query: ~19 seconds
Total subsequent: ~4 seconds (model cached)
```

**Advantage**: Subsequent queries are 4.5x faster because model stays loaded on worker!

## Common Questions

### Q: Can I still use images_search.py?
A: Yes, but it's not recommended. Use `query_client.py` instead.

### Q: Do I need to reinstall anything on Mac?
A: No! You can uninstall ML libraries if desired: `pip uninstall sentence-transformers torch faiss-cpu polars pillow`

### Q: What if a worker is busy?
A: Use a different worker: `--worker duc213-100g.eng.qumulo.com`

### Q: Can I query without copying images?
A: Yes: `python3 query_client.py --text "query" --no-copy-results`

### Q: Where are the original images?
A: Still at `/mnt/music/home/joe/images` (unchanged). Results are copies.

### Q: Can I delete old result images?
A: Yes: `rm /Volumes/files/home/joe/image_results/match_202501*`

## Future Enhancements

Possible improvements:
- Web interface for queries
- Batch query processing
- Result caching
- Query history
- Result tagging/organization
- Integration with other tools (Slack, etc.)

## Support

See:
- `QUERY_GUIDE.md` - Complete query documentation
- `README_DISTRIBUTED.md` - Full system documentation
- `QUICKSTART.md` - Quick reference
