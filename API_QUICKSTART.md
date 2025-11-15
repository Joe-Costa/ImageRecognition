# API Server Quick Start Guide

## Overview

This API allows external systems to notify duc17 of new images and track indexing progress.

## Key Endpoints

### 1. Add New Images
```bash
POST http://duc17-40g.eng.qumulo.com:8000/api/v1/index/add-images
```
External source calls this to notify of new images.

### 2. Check Job Status
```bash
GET http://duc17-40g.eng.qumulo.com:8000/api/v1/index/status/{job_id}
```
Returns progress: how many images processed, percentage complete.

### 3. Get Index Statistics
```bash
GET http://duc17-40g.eng.qumulo.com:8000/api/v1/index/stats
```
Returns total images in index, model info, index size.

### 4. Get Overall Status
```bash
GET http://duc17-40g.eng.qumulo.com:8000/api/v1/index/status
```
Returns system-wide status: active jobs, recent history, total images.

## Installation on duc17

### Step 1: Install API Dependencies

```bash
ssh root@duc17-40g.eng.qumulo.com

cd /root/ImageRecognition

# Activate venv
source venv/bin/activate

# Install FastAPI and uvicorn
pip install fastapi uvicorn[standard] pydantic python-multipart
```

### Step 2: Start the API Server

```bash
# Run in foreground (for testing)
python3 api_server.py

# Or run with uvicorn directly
uvicorn api_server:app --host 0.0.0.0 --port 8000

# Run in background
nohup python3 api_server.py > api_server.log 2>&1 &
```

### Step 3: Verify API is Running

```bash
# From another terminal
curl http://duc17-40g.eng.qumulo.com:8000/health

# Should return:
# {"status":"healthy","timestamp":"...","index_available":true}
```

### Step 4: View API Documentation

Open browser to:
```
http://duc17-40g.eng.qumulo.com:8000/docs
```

This provides interactive Swagger UI documentation.

## Usage Examples

### Example 1: External System Adds New Images

```python
import requests

# External system notifies of new images
response = requests.post(
    "http://duc17-40g.eng.qumulo.com:8000/api/v1/index/add-images",
    json={
        "image_paths": [
            "/mnt/music/home/joe/images/batch1/img001.jpg",
            "/mnt/music/home/joe/images/batch1/img002.jpg",
            "/mnt/music/home/joe/images/batch1/img003.jpg"
        ],
        "priority": "normal"
    }
)

result = response.json()
print(f"Job ID: {result['job_id']}")
print(f"New images: {result['new_images_count']}")
print(f"Already indexed: {result['already_indexed_count']}")
```

Response:
```json
{
  "job_id": "idx_20251114_143025",
  "status": "queued",
  "images_count": 3,
  "new_images_count": 3,
  "already_indexed_count": 0,
  "message": "Queued 3 new images for indexing"
}
```

### Example 2: Check Progress

```python
import time

job_id = "idx_20251114_143025"

while True:
    response = requests.get(
        f"http://duc17-40g.eng.qumulo.com:8000/api/v1/index/status/{job_id}"
    )

    status = response.json()

    if status["status"] == "completed":
        print("Indexing complete!")
        break

    if status["status"] == "failed":
        print(f"Indexing failed: {status['error_message']}")
        break

    if status.get("progress"):
        print(f"Progress: {status['progress']['percent_complete']}%")

    time.sleep(5)
```

Response while running:
```json
{
  "job_id": "idx_20251114_143025",
  "status": "running",
  "progress": {
    "total_images": 3,
    "processed_images": 2,
    "failed_images": 0,
    "percent_complete": 66.7
  },
  "started_at": "2025-11-14T14:30:26"
}
```

### Example 3: Get Total Images in Index

```python
response = requests.get(
    "http://duc17-40g.eng.qumulo.com:8000/api/v1/index/stats"
)

stats = response.json()
print(f"Total images in index: {stats['total_images']}")
print(f"Model: {stats['model_name']}")
print(f"Index size: {stats['index_size_mb']} MB")
```

Response:
```json
{
  "model_name": "clip-ViT-L-14",
  "embedding_dim": 768,
  "total_images": 118323,
  "num_failed": 0,
  "last_updated": "2025-11-14T08:05:00",
  "index_size_mb": 739.5
}
```

### Example 4: Using the Test Client

```bash
# On your Mac or duc17
python3 test_api_client.py
```

This demonstrates the complete workflow:
1. Get current stats
2. Submit new images
3. Monitor progress
4. Get updated stats

## Workflow Summary

```
External System                    duc17 API                      Workers
     │                                │                              │
     │  POST /add-images              │                              │
     │  (new image paths)             │                              │
     ├───────────────────────────────>│                              │
     │                                │  Create job                  │
     │                                │  Filter already-indexed      │
     │  Response: job_id              │  Queue for processing        │
     │<───────────────────────────────┤                              │
     │                                │                              │
     │  GET /status/{job_id}          │                              │
     │  (check progress)              │  Distribute work             │
     ├───────────────────────────────>├─────────────────────────────>│
     │                                │                              │
     │  Response: 33% complete        │  Monitor workers             │
     │<───────────────────────────────┤                              │
     │                                │                              │
     │  GET /status/{job_id}          │  Collect results             │
     ├───────────────────────────────>│  Merge indexes               │
     │                                │  Update state                │
     │  Response: 100% complete       │                              │
     │<───────────────────────────────┤                              │
     │                                │                              │
     │  GET /stats                    │                              │
     │  (total images)                │                              │
     ├───────────────────────────────>│                              │
     │                                │                              │
     │  Response: 118,326 images      │                              │
     │<───────────────────────────────┤                              │
```

## Current Limitations (MVP)

1. **Simulated Processing**: The background job currently simulates work. Next step is to integrate with actual `controller.py` logic.

2. **In-Memory Jobs**: Job status is stored in memory. Restart will lose job history (but state file persists indexed images).

3. **No Authentication**: API key validation is stubbed out for development.

4. **Single Instance**: Only one API server instance supported (no load balancing yet).

## Next Steps

1. **Integrate Real Indexing**: Replace simulated background task with actual controller logic
2. **Persistent Job Queue**: Use Redis or database for job tracking
3. **Enable Authentication**: Implement proper API key validation
4. **Add Systemd Service**: Auto-start API on boot
5. **Add Logging**: Structured logging to files
6. **Add Metrics**: Prometheus metrics endpoint

## Troubleshooting

### API won't start
```bash
# Check if port 8000 is in use
netstat -tlnp | grep 8000

# Kill existing process
pkill -f api_server
```

### Can't connect from Mac
```bash
# Check firewall on duc17
sudo ufw status

# Allow port 8000
sudo ufw allow 8000/tcp
```

### State file issues
```bash
# Check state file
cat /mnt/music/home/joe/imageindex.state.json

# Reset state (warning: loses indexed image tracking)
rm /mnt/music/home/joe/imageindex.state.json
```

## Files Created

- `api_server.py` - Main FastAPI application
- `test_api_client.py` - Example Python client
- `requirements-api.txt` - API dependencies
- `API_QUICKSTART.md` - This guide
