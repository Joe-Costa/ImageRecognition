# Image Search Query Guide for LLMs

This document explains how to query the distributed CLIP-based image search system and retrieve matching image paths programmatically.

## System Overview

The image search system uses CLIP (Contrastive Language-Image Pre-training) to enable semantic image search across 118,323 indexed images from the COCO train2017 dataset. The system uses a client-server architecture where queries are submitted from a Mac client to remote worker hosts that perform the actual search.

## Architecture

- **Index Location**: `/mnt/music/home/joe/imageindex.*` (on NFS mount)
- **Image Location**: `/mnt/music/home/joe/images/` (on NFS mount)
- **Model**: clip-ViT-L-14 (768-dimensional embeddings)
- **Search Method**: Faiss vector similarity (IndexFlatIP)
- **Default Worker**: duc17-40g.eng.qumulo.com (62GB RAM)

## Quick Start: Issuing Queries

### Method 1: Using the Query Client (Recommended)

The simplest way to issue queries is using `query_client.py`:

```bash
python3 query_client.py --text "your search query" --top-k 10
```

**Parameters:**
- `--text` (required): Natural language description of what you're looking for
- `--top-k` (optional): Number of results to return (default: 10)
- `--worker` (optional): Worker host to run query on (default: duc17-40g.eng.qumulo.com)
- `--copy-results` (optional): Copy matching images to results directory (default: true)
- `--no-copy-results` (optional): Only display paths, don't copy images

**Example:**
```bash
python3 query_client.py --text "people walking in a park" --top-k 5
```

### Method 2: Direct Remote Execution

For programmatic access, you can SSH directly to a worker and execute queries:

```bash
ssh root@duc17-40g.eng.qumulo.com \
  "cd /root/ImageRecognition && \
   venv/bin/python remote_query.py \
   --index-prefix /mnt/music/home/joe/imageindex \
   --text 'dogs playing' \
   --top-k 10 \
   --results-dir /mnt/music/home/joe/image_results \
   --no-copy-results"
```

## Retrieving Result Paths

### Output Format

Query results are printed to stdout in this format:

```
[2025-11-14 16:38:36] [Query] Search Results:
[2025-11-14 16:38:36] [Query] --------------------------------------------------------------------------------
[2025-11-14 16:38:36] [Query]    1. score=0.2252  /mnt/music/home/joe/images/coco_train2017/train2017/000000097989.jpg
[2025-11-14 16:38:36] [Query]    2. score=0.2178  /mnt/music/home/joe/images/coco_train2017/train2017/000000563475.jpg
[2025-11-14 16:38:36] [Query]    3. score=0.2153  /mnt/music/home/joe/images/coco_train2017/train2017/000000445892.jpg
```

### Parsing Results Programmatically

To parse query results from the output:

```python
import subprocess
import re

def query_images(query_text: str, top_k: int = 10) -> list[tuple[int, float, str]]:
    """
    Execute image search query and return ranked results.

    Returns:
        List of tuples: (rank, score, image_path)
    """
    cmd = [
        "python3", "query_client.py",
        "--text", query_text,
        "--top-k", str(top_k),
        "--no-copy-results"  # Only get paths, don't copy
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Parse output for result lines
    # Format: "   1. score=0.2252  /path/to/image.jpg"
    pattern = r'\s+(\d+)\.\s+score=([\d.]+)\s+(.+\.jpg)'

    matches = re.findall(pattern, result.stdout)

    results = []
    for rank_str, score_str, path in matches:
        results.append((int(rank_str), float(score_str), path))

    return results

# Usage
results = query_images("people walking", top_k=5)
for rank, score, path in results:
    print(f"Rank {rank}: {score:.4f} - {path}")
```

### Using Bash Tool to Issue Queries

When using the Bash tool to issue queries:

```python
# Example tool call
Bash(
    command='python3 query_client.py --text "sunset over mountains" --top-k 5 --no-copy-results',
    description="Search for sunset images"
)
```

The output will contain paths in the format shown above. Extract them using regex or string parsing.

## Understanding Scores

- **Score Range**: 0.0 to 1.0 (higher is better)
- **Typical Good Matches**: 0.20 - 0.35
- **Excellent Matches**: 0.35+
- **Weak Matches**: < 0.15

Scores represent cosine similarity between the query embedding and image embeddings in the CLIP latent space.

## Path Translation

Image paths are returned in NFS mount format:
```
/mnt/music/home/joe/images/coco_train2017/train2017/000000097989.jpg
```

If accessing from Mac via SMB mount:
```
/Volumes/files/home/joe/images/coco_train2017/train2017/000000097989.jpg
```

## Advanced: Direct Python Access

For applications that need direct Python access to the index:

```python
import json
import numpy as np
import polars as pl
import faiss
from sentence_transformers import SentenceTransformer
from pathlib import Path

# Load index
index_prefix = Path("/mnt/music/home/joe/imageindex")

# Load metadata
with open(f"{index_prefix}.meta.json") as f:
    meta = json.load(f)
    model_name = meta["model_name"]  # "clip-ViT-L-14"

# Load image paths and embeddings
df = pl.read_parquet(f"{index_prefix}.parquet")
paths = df["path"].to_list()
embeddings = np.array(df["embedding"].to_list(), dtype="float32")

# Load Faiss index
index = faiss.read_index(f"{index_prefix}.faiss")

# Load CLIP model
model = SentenceTransformer(model_name, device="cpu")

# Encode query
query_embedding = model.encode(
    "your query text",
    convert_to_numpy=True,
    normalize_embeddings=True,
    show_progress_bar=False
).astype("float32").reshape(1, -1)

# Search
top_k = 10
scores, indices = index.search(query_embedding, top_k)

# Get results
for rank, (score, idx) in enumerate(zip(scores[0], indices[0]), start=1):
    print(f"{rank}. {score:.4f} - {paths[idx]}")
```

## Performance Characteristics

- **Query Time**: ~12-13 seconds per query
  - 10 seconds: Loading Parquet index (118k images)
  - 2-3 seconds: Model loading and inference
  - < 1 second: Vector search

- **Index Size**:
  - Faiss index: 347MB
  - Parquet metadata: 392MB
  - Total: ~740MB

- **Bottlenecks**:
  - Loading Parquet file dominates query time
  - Consider keeping worker process running for repeated queries
  - Model loading is cached after first query in same session

## Query Examples

### Simple Object Queries
```bash
python3 query_client.py --text "dogs" --top-k 10
python3 query_client.py --text "cars" --top-k 10
python3 query_client.py --text "bicycles" --top-k 10
```

### Complex Scene Queries
```bash
python3 query_client.py --text "people walking in a park" --top-k 5
python3 query_client.py --text "sunset over mountains" --top-k 5
python3 query_client.py --text "rainy city street at night" --top-k 5
```

### Attribute-Based Queries
```bash
python3 query_client.py --text "red car" --top-k 5
python3 query_client.py --text "small dog" --top-k 5
python3 query_client.py --text "crowded beach" --top-k 5
```

## Troubleshooting

### Query Returns Poor Results

- Try more descriptive queries with context
- Increase `--top-k` to see more results
- Remember: CLIP is trained on web images, so use natural descriptions

### SSH Connection Fails

```bash
# Test SSH connectivity
ssh root@duc17-40g.eng.qumulo.com "echo 'OK'"
```

### Index Files Not Found

Verify index exists:
```bash
ls -lh /Volumes/files/home/joe/imageindex.*
```

Should show:
- `imageindex.faiss` (347MB)
- `imageindex.parquet` (392MB)
- `imageindex.meta.json` (1.1KB)

### Performance Issues

- Queries are CPU-bound on model inference
- Use high-RAM worker (duc17) for better performance
- First query in a session is slower due to model loading

## Integration Tips for LLMs

1. **Use `--no-copy-results`** when you only need paths, not actual images
2. **Parse stdout** to extract paths and scores using regex
3. **Batch queries** by keeping SSH connection alive
4. **Handle timeouts** - queries typically complete in 15-20 seconds
5. **Validate paths** exist before attempting to access images
6. **Use Bash tool** with capture_output=True to parse results programmatically

## System Metadata

Current index statistics (as of 2025-11-14):

```json
{
  "model_name": "clip-ViT-L-14",
  "embedding_dim": 768,
  "num_images": 118323,
  "num_failed": 0,
  "num_workers": 4,
  "total_processing_time_seconds": 89601.83,
  "merge_time_seconds": 15.87
}
```

## Contact and Updates

- Repository: https://github.com/Joe-Costa/ImageRecognition
- Update workers: `./update_workers.sh`
- Re-index: `./auto_index_coco.sh`
