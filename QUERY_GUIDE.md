# Query System Guide

## Overview

The query system runs entirely on remote workers - your Mac only needs Python's standard library (no ML dependencies). Queries execute on workers and matching images are automatically copied to a results directory with timestamped names.

## Quick Start

```bash
# Simple query
python3 query_client.py --text "sunset over mountains"

# View results on Mac
open /Volumes/home/joe/image_results
```

## Architecture

```
Mac (you)
    |
    | SSH: Send query text
    |
Worker (duc17-40g by default)
    |
    | 1. Load index & CLIP model
    | 2. Encode query text
    | 3. Search for matches
    | 4. Copy images to results dir
    | 5. Rename: match_YYYYMMDD_HHMMSS_rank001.jpg
    |
NFS: /mnt/music/home/joe/image_results
    |
    | (accessible via SMB on Mac)
    |
Mac: /Volumes/home/joe/image_results
```

## Usage Examples

### Basic Queries

```bash
# Find cars
python3 query_client.py --text "red sports car"

# Find landscapes
python3 query_client.py --text "mountain landscape with lake"

# Find people
python3 query_client.py --text "person smiling"

# Find specific scenes
python3 query_client.py --text "sunset on the beach"
```

### Advanced Options

```bash
# Get more results
python3 query_client.py --text "cat" --top-k 20

# Use specific worker
python3 query_client.py \
    --text "dog" \
    --worker duc212-100g.eng.qumulo.com

# Just display matches without copying
python3 query_client.py \
    --text "tree" \
    --no-copy-results

# Combine options
python3 query_client.py \
    --text "flower" \
    --top-k 15 \
    --worker duc17-40g.eng.qumulo.com
```

## Result Files

Matching images are copied to:
- **Remote**: `/mnt/music/home/joe/image_results/`
- **Mac**: `/Volumes/home/joe/image_results/`

File naming format:
```
match_20250113_143022_rank001.jpg  <- Best match
match_20250113_143022_rank002.jpg  <- 2nd best
match_20250113_143022_rank003.jpg  <- 3rd best
...
```

Where:
- `20250113` = Date (YYYYMMDD)
- `143022` = Time (HHMMSS)
- `rank001` = Search result rank

## Command Reference

### query_client.py (Mac)

| Option | Description | Default |
|--------|-------------|---------|
| `--text` | Query text (required) | - |
| `--top-k` | Number of results | 10 |
| `--worker` | Worker hostname | duc17-40g.eng.qumulo.com |
| `--copy-results` | Copy images to results dir | True |
| `--no-copy-results` | Don't copy images | False |

### Available Workers

| Worker | RAM | Speed | Best For |
|--------|-----|-------|----------|
| duc17-40g | 62GB | Fast | Large queries, default |
| duc212-100g | 15GB | Medium | - |
| duc213-100g | 15GB | Medium | - |
| duc214-100g | 15GB | Medium | - |

## Workflow

1. **Submit Query** (Mac)
   ```bash
   python3 query_client.py --text "your query here"
   ```

2. **Worker Processes** (Automatic)
   - Loads index files
   - Loads CLIP model (cached after first query)
   - Encodes query text
   - Searches vector index
   - Finds top-K matches

3. **Copy Results** (Automatic)
   - Worker copies matched images to results directory
   - Renames with timestamp and rank
   - Preserves original file extension

4. **View Results** (Mac)
   ```bash
   # Open in Finder
   open /Volumes/home/joe/image_results

   # List recent results
   ls -lth /Volumes/home/joe/image_results | head -20

   # View specific query's results
   ls /Volumes/home/joe/image_results/match_20250113_143022_*
   ```

## Performance

### Query Speed

| Component | Time |
|-----------|------|
| First query (model load) | ~10-20 seconds |
| Subsequent queries | ~2-5 seconds |
| Image copying (per image) | <0.1 seconds |

**Example**: Query for 10 images
- First time: ~15 seconds total
- Later queries: ~3 seconds total

### Tips for Faster Queries

1. **Use duc17-40g** (default) - has most RAM
2. **Keep queries short** - "sunset" vs "beautiful sunset over ocean with clouds"
3. **Reuse same worker** - CLIP model stays loaded in memory
4. **Limit results** - Use `--top-k 5` if you only need a few matches

## Troubleshooting

### SSH Connection Failed

```bash
# Test SSH manually
ssh root@duc17-40g.eng.qumulo.com "echo OK"

# If fails, check your SSH keys
ls -la ~/.ssh/
```

### No Results Found

The query is working, but no good matches. Try:
- Different query text
- More results: `--top-k 20`
- Broader terms: "car" instead of "red 1967 mustang"

### Results Not Visible on Mac

```bash
# Check if SMB mount is active
ls /Volumes/home/joe/image_results

# If not mounted, remount SMB share
# (Finder -> Go -> Connect to Server -> smb://your-server/home/joe)
```

### Worker Out of Memory

Use a different worker with more RAM:
```bash
python3 query_client.py \
    --text "your query" \
    --worker duc17-40g.eng.qumulo.com
```

### Remote Script Not Found

Query client will auto-deploy `remote_query.py` on first run. If it fails:
```bash
# Manually deploy
scp remote_query.py root@duc17-40g.eng.qumulo.com:/root/image_detection/
```

## Managing Results

### View All Results

```bash
# List all result files
ls -lh /Volumes/home/joe/image_results

# Count total results
ls /Volumes/home/joe/image_results/match_*.jpg | wc -l
```

### Find Results by Date

```bash
# Today's results
ls /Volumes/home/joe/image_results/match_$(date +%Y%m%d)_*

# Specific date (e.g., Jan 13, 2025)
ls /Volumes/home/joe/image_results/match_20250113_*

# Last hour
find /Volumes/home/joe/image_results -name "match_*.jpg" -mmin -60
```

### Clean Up Old Results

```bash
# Delete all results
rm /Volumes/home/joe/image_results/match_*

# Delete results older than 7 days
find /Volumes/home/joe/image_results -name "match_*" -mtime +7 -delete

# Delete specific query's results
rm /Volumes/home/joe/image_results/match_20250113_143022_*
```

### Organize Results by Query

```bash
# Create subdirectory for a query
mkdir -p /Volumes/home/joe/image_results/cars
mv /Volumes/home/joe/image_results/match_20250113_143022_* \
   /Volumes/home/joe/image_results/cars/
```

## Direct Worker Queries (Advanced)

If you want to run queries directly on a worker (bypassing the Mac client):

```bash
# SSH to worker
ssh root@duc17-40g.eng.qumulo.com

# Run query directly
cd /root/ImageRecognition
python3 remote_query.py \
    --index-prefix /mnt/music/home/joe/imageindex \
    --text "sunset" \
    --top-k 10 \
    --results-dir /mnt/music/home/joe/image_results
```

## Query Tips

### Good Queries

- **Specific objects**: "red car", "black cat", "white dog"
- **Scenes**: "sunset", "beach", "mountain", "city street"
- **Actions**: "person running", "bird flying", "car driving"
- **Compositions**: "close-up face", "wide landscape", "aerial view"

### Queries That Work Less Well

- **Abstract concepts**: "happiness", "freedom" (unless visually obvious)
- **Text in images**: "stop sign with word 'STOP'" (CLIP doesn't read text well)
- **Very specific details**: "2003 Honda Accord EX" (try "silver sedan" instead)
- **Negations**: "not a car" (doesn't work, phrase positively)

### Improving Results

1. **Try variations**:
   - "automobile" vs "car"
   - "feline" vs "cat"
   - "ocean" vs "sea" vs "water"

2. **Add context**:
   - "golden retriever" vs just "dog"
   - "sunset beach" vs just "sunset"

3. **Simplify**:
   - "red sports car" vs "red Ferrari F40 sports car"

## Integration Examples

### Slack Bot (Future)

```bash
# Example: User types "/find sunset"
# Bot runs: python3 query_client.py --text "$user_query" --top-k 5
# Bot posts result images to Slack
```

### Web Interface (Future)

```html
<!-- User enters query in web form -->
<!-- Backend runs query_client.py -->
<!-- Results displayed as gallery -->
```

### Batch Queries (Current)

```bash
# Query multiple things at once
for query in "sunset" "car" "cat" "dog" "tree"; do
    echo "Searching for: $query"
    python3 query_client.py --text "$query" --top-k 5
done
```

## See Also

- `README_DISTRIBUTED.md` - Full system documentation
- `QUICKSTART.md` - Quick reference guide
- `controller.py` - For re-indexing images
