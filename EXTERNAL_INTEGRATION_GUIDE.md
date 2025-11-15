# External System Integration Guide

## Overview

This document explains how to integrate your application with the Image Indexing API running on duc17-40g.eng.qumulo.com. Your system will:

1. Notify the API when new image files are available
2. Monitor indexing progress
3. Query index statistics

## Prerequisites

Your system must be able to:
- Make HTTP requests (REST API calls)
- Access duc17-40g.eng.qumulo.com on port 8000
- Provide absolute file paths on the NFS mount (`/mnt/music/home/joe/images/...`)

## API Base URL

```
http://duc17-40g.eng.qumulo.com:8000
```

All endpoints are prefixed with `/api/v1`.

## Core Workflow

```
Your Application                        duc17 API                    Index
      |                                      |                         |
      | Detect new image files               |                         |
      |------------------------------------->|                         |
      | POST /api/v1/index/add-images        |                         |
      | {image_paths: [...]}                 |                         |
      |                                      | Create job              |
      |                                      | Filter duplicates       |
      | Response: {job_id, new_count}        |                         |
      |<-------------------------------------|                         |
      |                                      |                         |
      | Poll for progress                    | Process images          |
      | GET /status/{job_id}                 | Update progress         |
      |------------------------------------->|------------------------>|
      |                                      |                         |
      | Response: {status, percent}          |                         |
      |<-------------------------------------|                         |
      |                                      |                         |
      | Repeat until complete                |                         |
      |                                      | Merge to main index     |
      |                                      |------------------------>|
      | GET /stats                           |                         |
      |------------------------------------->|                         |
      | Response: {total_images}             |                         |
      |<-------------------------------------|                         |
```

## API Endpoints

### 1. Submit New Images for Indexing

**Endpoint:** `POST /api/v1/index/add-images`

**Purpose:** Notify the API that new images are available to be indexed.

**Request:**
```json
{
  "image_paths": [
    "/mnt/music/home/joe/images/batch1/image001.jpg",
    "/mnt/music/home/joe/images/batch1/image002.jpg",
    "/mnt/music/home/joe/images/batch2/photo.png"
  ],
  "priority": "normal"
}
```

**Request Fields:**
- `image_paths` (required): Array of absolute file paths on NFS mount
- `priority` (optional): "low", "normal", or "high" (default: "normal")

**Response:**
```json
{
  "job_id": "idx_20251114_143025",
  "status": "queued",
  "images_count": 3,
  "new_images_count": 1,
  "already_indexed_count": 2,
  "message": "Queued 1 new images for indexing"
}
```

**Response Fields:**
- `job_id`: Unique identifier for this indexing job (use to check progress)
- `status`: Current job status ("queued", "running", "completed", "failed")
- `images_count`: Total images you submitted
- `new_images_count`: How many are new (not already indexed)
- `already_indexed_count`: How many were already in the index
- `message`: Human-readable status message

**Special Case:** If all images are already indexed:
```json
{
  "job_id": "none",
  "status": "completed",
  "images_count": 3,
  "new_images_count": 0,
  "already_indexed_count": 3,
  "message": "All images already indexed"
}
```

When `job_id` is "none", no indexing job was created.

### 2. Check Job Progress

**Endpoint:** `GET /api/v1/index/status/{job_id}`

**Purpose:** Check the progress of a specific indexing job.

**Request:**
```
GET /api/v1/index/status/idx_20251114_143025
```

**Response (Job Running):**
```json
{
  "job_id": "idx_20251114_143025",
  "status": "running",
  "progress": {
    "total_images": 100,
    "processed_images": 47,
    "failed_images": 2,
    "percent_complete": 47.0
  },
  "started_at": "2025-11-14T14:30:26Z",
  "completed_at": null,
  "error_message": null
}
```

**Response (Job Completed):**
```json
{
  "job_id": "idx_20251114_143025",
  "status": "completed",
  "progress": {
    "total_images": 100,
    "processed_images": 98,
    "failed_images": 2,
    "percent_complete": 100.0
  },
  "started_at": "2025-11-14T14:30:26Z",
  "completed_at": "2025-11-14T14:45:18Z",
  "error_message": null
}
```

**Response (Job Failed):**
```json
{
  "job_id": "idx_20251114_143025",
  "status": "failed",
  "progress": {
    "total_images": 100,
    "processed_images": 23,
    "failed_images": 77,
    "percent_complete": 23.0
  },
  "started_at": "2025-11-14T14:30:26Z",
  "completed_at": "2025-11-14T14:32:15Z",
  "error_message": "Worker connection failed"
}
```

**Status Values:**
- `queued`: Job created but not started yet
- `running`: Job actively processing images
- `completed`: All images processed successfully
- `failed`: Job encountered fatal error

**Polling Recommendations:**
- Poll every 5-10 seconds while job is running
- Stop polling when status is "completed" or "failed"
- Use exponential backoff for long-running jobs

### 3. Get Index Statistics

**Endpoint:** `GET /api/v1/index/stats`

**Purpose:** Get information about the current index (total images, model info, size).

**Request:**
```
GET /api/v1/index/stats
```

**Response:**
```json
{
  "model_name": "clip-ViT-L-14",
  "embedding_dim": 768,
  "total_images": 118323,
  "num_failed": 0,
  "last_updated": "2025-11-14T08:05:00Z",
  "index_size_mb": 739.5
}
```

**Response Fields:**
- `model_name`: CLIP model used for embeddings
- `embedding_dim`: Dimensionality of embeddings (768 for ViT-L-14)
- `total_images`: Total number of images currently in the index
- `num_failed`: Number of images that failed to index
- `last_updated`: ISO timestamp of last index update
- `index_size_mb`: Total size of index files in megabytes

### 4. Get Overall System Status

**Endpoint:** `GET /api/v1/index/status`

**Purpose:** Get system-wide status including active jobs and recent history.

**Request:**
```
GET /api/v1/index/status
```

**Response:**
```json
{
  "total_indexed_images": 118323,
  "active_jobs": 2,
  "active_job_details": [
    {
      "job_id": "idx_20251114_143025",
      "status": "running",
      "created_at": "2025-11-14T14:30:25Z"
    },
    {
      "job_id": "idx_20251114_144500",
      "status": "queued",
      "created_at": "2025-11-14T14:45:00Z"
    }
  ],
  "recent_jobs": [
    {
      "job_id": "idx_20251114_120000",
      "status": "completed",
      "created_at": "2025-11-14T12:00:00Z",
      "images": 1000
    }
  ],
  "index_stats": {
    "model_name": "clip-ViT-L-14",
    "total_images": 118323,
    "num_failed": 0,
    "last_updated": "2025-11-14T08:05:00Z",
    "index_size_mb": 739.5
  }
}
```

**Response Fields:**
- `total_indexed_images`: Current total in index
- `active_jobs`: Number of jobs currently queued or running
- `active_job_details`: Details of each active job
- `recent_jobs`: Last 10 completed/failed jobs
- `index_stats`: Same as `/stats` endpoint

### 5. Health Check

**Endpoint:** `GET /health`

**Purpose:** Verify API is running and index is available.

**Request:**
```
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-11-14T14:30:25Z",
  "index_available": true
}
```

## Implementation Examples

### Python Implementation

```python
import requests
import time
from typing import List, Dict, Optional


class ImageIndexAPI:
    """Client for the Image Indexing API."""

    def __init__(self, base_url: str = "http://duc17-40g.eng.qumulo.com:8000"):
        self.base_url = base_url.rstrip('/')

    def add_images(self, image_paths: List[str], priority: str = "normal") -> Dict:
        """
        Submit new images for indexing.

        Args:
            image_paths: List of absolute paths on NFS mount
            priority: "low", "normal", or "high"

        Returns:
            Response dict with job_id and status
        """
        response = requests.post(
            f"{self.base_url}/api/v1/index/add-images",
            json={
                "image_paths": image_paths,
                "priority": priority
            }
        )
        response.raise_for_status()
        return response.json()

    def get_job_status(self, job_id: str) -> Dict:
        """Get status of a specific job."""
        response = requests.get(
            f"{self.base_url}/api/v1/index/status/{job_id}"
        )
        response.raise_for_status()
        return response.json()

    def get_index_stats(self) -> Dict:
        """Get current index statistics."""
        response = requests.get(
            f"{self.base_url}/api/v1/index/stats"
        )
        response.raise_for_status()
        return response.json()

    def get_overall_status(self) -> Dict:
        """Get overall system status."""
        response = requests.get(
            f"{self.base_url}/api/v1/index/status"
        )
        response.raise_for_status()
        return response.json()

    def wait_for_job(
        self,
        job_id: str,
        poll_interval: int = 5,
        timeout: int = 3600,
        progress_callback: Optional[callable] = None
    ) -> Dict:
        """
        Wait for a job to complete.

        Args:
            job_id: Job ID to monitor
            poll_interval: Seconds between checks
            timeout: Maximum seconds to wait
            progress_callback: Function called with progress dict

        Returns:
            Final job status dict
        """
        start_time = time.time()

        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Job {job_id} exceeded timeout of {timeout}s")

            status = self.get_job_status(job_id)

            # Call progress callback if provided
            if progress_callback and status.get("progress"):
                progress_callback(status["progress"])

            # Check if job is done
            if status["status"] in ["completed", "failed"]:
                return status

            time.sleep(poll_interval)


# Example usage
def main():
    api = ImageIndexAPI()

    # 1. Check current index stats
    stats = api.get_index_stats()
    print(f"Current index has {stats['total_images']} images")

    # 2. Submit new images
    new_images = [
        "/mnt/music/home/joe/images/batch1/img001.jpg",
        "/mnt/music/home/joe/images/batch1/img002.jpg",
    ]

    result = api.add_images(new_images)

    if result["job_id"] == "none":
        print("All images already indexed")
        return

    job_id = result["job_id"]
    print(f"Created job {job_id} with {result['new_images_count']} new images")

    # 3. Monitor progress
    def show_progress(progress):
        print(f"Progress: {progress['percent_complete']}% "
              f"({progress['processed_images']}/{progress['total_images']})")

    final_status = api.wait_for_job(job_id, progress_callback=show_progress)

    # 4. Check final status
    if final_status["status"] == "completed":
        print(f"Indexing completed successfully!")
        print(f"Processed: {final_status['progress']['processed_images']}")
        print(f"Failed: {final_status['progress']['failed_images']}")

        # Get updated stats
        stats = api.get_index_stats()
        print(f"Index now has {stats['total_images']} images")
    else:
        print(f"Indexing failed: {final_status['error_message']}")


if __name__ == "__main__":
    main()
```

### Bash/curl Implementation

```bash
#!/bin/bash

API_URL="http://duc17-40g.eng.qumulo.com:8000"

# 1. Check health
echo "Checking API health..."
curl -s "${API_URL}/health" | jq .

# 2. Get current stats
echo "Getting index stats..."
STATS=$(curl -s "${API_URL}/api/v1/index/stats")
echo "$STATS" | jq .
TOTAL_IMAGES=$(echo "$STATS" | jq -r '.total_images')
echo "Current index has $TOTAL_IMAGES images"

# 3. Submit new images
echo "Submitting new images..."
RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/index/add-images" \
  -H "Content-Type: application/json" \
  -d '{
    "image_paths": [
      "/mnt/music/home/joe/images/test1.jpg",
      "/mnt/music/home/joe/images/test2.jpg"
    ],
    "priority": "normal"
  }')

echo "$RESPONSE" | jq .

JOB_ID=$(echo "$RESPONSE" | jq -r '.job_id')

if [ "$JOB_ID" = "none" ]; then
  echo "All images already indexed"
  exit 0
fi

echo "Job ID: $JOB_ID"

# 4. Poll for completion
echo "Monitoring job progress..."
while true; do
  STATUS=$(curl -s "${API_URL}/api/v1/index/status/${JOB_ID}")

  JOB_STATUS=$(echo "$STATUS" | jq -r '.status')
  PERCENT=$(echo "$STATUS" | jq -r '.progress.percent_complete // 0')

  echo "Status: $JOB_STATUS - Progress: ${PERCENT}%"

  if [ "$JOB_STATUS" = "completed" ] || [ "$JOB_STATUS" = "failed" ]; then
    echo "$STATUS" | jq .
    break
  fi

  sleep 5
done

# 5. Get updated stats
echo "Getting updated index stats..."
curl -s "${API_URL}/api/v1/index/stats" | jq .
```

### JavaScript/Node.js Implementation

```javascript
const axios = require('axios');

class ImageIndexAPI {
  constructor(baseUrl = 'http://duc17-40g.eng.qumulo.com:8000') {
    this.baseUrl = baseUrl;
  }

  async addImages(imagePaths, priority = 'normal') {
    const response = await axios.post(`${this.baseUrl}/api/v1/index/add-images`, {
      image_paths: imagePaths,
      priority: priority
    });
    return response.data;
  }

  async getJobStatus(jobId) {
    const response = await axios.get(`${this.baseUrl}/api/v1/index/status/${jobId}`);
    return response.data;
  }

  async getIndexStats() {
    const response = await axios.get(`${this.baseUrl}/api/v1/index/stats`);
    return response.data;
  }

  async waitForJob(jobId, pollInterval = 5000, timeout = 3600000) {
    const startTime = Date.now();

    while (true) {
      if (Date.now() - startTime > timeout) {
        throw new Error(`Job ${jobId} exceeded timeout`);
      }

      const status = await this.getJobStatus(jobId);

      if (status.progress) {
        console.log(`Progress: ${status.progress.percent_complete}%`);
      }

      if (status.status === 'completed' || status.status === 'failed') {
        return status;
      }

      await new Promise(resolve => setTimeout(resolve, pollInterval));
    }
  }
}

// Example usage
async function main() {
  const api = new ImageIndexAPI();

  try {
    // Get current stats
    const stats = await api.getIndexStats();
    console.log(`Current index: ${stats.total_images} images`);

    // Submit new images
    const result = await api.addImages([
      '/mnt/music/home/joe/images/test1.jpg',
      '/mnt/music/home/joe/images/test2.jpg'
    ]);

    if (result.job_id === 'none') {
      console.log('All images already indexed');
      return;
    }

    console.log(`Job created: ${result.job_id}`);

    // Wait for completion
    const finalStatus = await api.waitForJob(result.job_id);

    if (finalStatus.status === 'completed') {
      console.log('Indexing completed!');
      const updatedStats = await api.getIndexStats();
      console.log(`Index now has ${updatedStats.total_images} images`);
    } else {
      console.log(`Indexing failed: ${finalStatus.error_message}`);
    }
  } catch (error) {
    console.error('Error:', error.message);
  }
}

main();
```

## Integration Patterns

### Pattern 1: Event-Driven Integration

Your application detects new image files and immediately notifies the API:

```python
def on_new_images_detected(image_paths: List[str]):
    """Called when your application detects new image files."""
    api = ImageIndexAPI()

    # Submit for indexing
    result = api.add_images(image_paths)

    if result["job_id"] != "none":
        # Log job ID for later tracking
        log_indexing_job(result["job_id"], image_paths)

        # Optionally: start async monitoring
        monitor_job_async(result["job_id"])
```

### Pattern 2: Batch Processing

Your application periodically checks for new images and submits in batches:

```python
import schedule

def process_new_images_batch():
    """Runs periodically to find and submit new images."""
    api = ImageIndexAPI()

    # Get list of new images (your logic)
    new_images = find_new_images_since_last_run()

    if not new_images:
        print("No new images found")
        return

    # Submit to API
    result = api.add_images(new_images)

    if result["new_images_count"] > 0:
        print(f"Submitted {result['new_images_count']} new images")
        # Wait for completion
        api.wait_for_job(result["job_id"])
    else:
        print("All images already indexed")

# Run every hour
schedule.every().hour.do(process_new_images_batch)
```

### Pattern 3: Progress Reporting

Your application shows progress to users:

```python
def index_with_progress_bar(image_paths: List[str]):
    """Index images and show progress bar to user."""
    api = ImageIndexAPI()

    result = api.add_images(image_paths)

    if result["job_id"] == "none":
        print("Images already indexed")
        return

    job_id = result["job_id"]

    # Show progress bar
    from tqdm import tqdm
    pbar = tqdm(total=100, desc="Indexing", unit="%")

    def update_progress(progress):
        pbar.n = progress["percent_complete"]
        pbar.refresh()

    api.wait_for_job(job_id, progress_callback=update_progress)
    pbar.close()
```

## Path Requirements

**CRITICAL:** Image paths must be absolute paths on the NFS mount as seen by duc17.

**Correct paths:**
```
/mnt/music/home/joe/images/batch1/img001.jpg
/mnt/music/home/joe/images/photos/vacation.png
```

**Incorrect paths:**
```
./images/img001.jpg                          # Relative path
/Users/joe/images/img001.jpg                 # Mac local path
/Volumes/files/home/joe/images/img001.jpg    # SMB mount path
```

If your application runs on Mac and uses SMB mount paths, translate them:

```python
def translate_to_nfs_path(smb_path: str) -> str:
    """Convert Mac SMB path to Linux NFS path."""
    # /Volumes/files/home/joe/images/... -> /mnt/music/home/joe/images/...
    return smb_path.replace("/Volumes/files", "/mnt/music")
```

## Error Handling

### HTTP Status Codes

- `200 OK` - Request succeeded
- `202 Accepted` - Job created and queued
- `404 Not Found` - Job ID not found
- `422 Unprocessable Entity` - Invalid request data
- `500 Internal Server Error` - Server error

### Handling Errors

```python
import requests

try:
    result = api.add_images(image_paths)
except requests.exceptions.ConnectionError:
    # API server not reachable
    print("Cannot connect to API server")
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 404:
        print("Job not found")
    elif e.response.status_code == 422:
        print(f"Invalid request: {e.response.json()}")
    else:
        print(f"HTTP error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Performance Considerations

### Batch Size

- **Small batches (1-100 images)**: Submit immediately, low latency
- **Medium batches (100-1000 images)**: Process in minutes
- **Large batches (1000+ images)**: Process in hours, consider splitting

### Polling Frequency

- Start with 5 second intervals
- Increase to 10-30 seconds for long-running jobs
- Use exponential backoff to reduce load

### Concurrent Jobs

The API can handle multiple concurrent jobs. Your application can submit new batches while previous ones are still processing.

## Testing Your Integration

### 1. Test API Connectivity

```bash
curl http://duc17-40g.eng.qumulo.com:8000/health
```

Expected response:
```json
{"status": "healthy", "timestamp": "...", "index_available": true}
```

### 2. Test with Sample Images

```python
# Use existing indexed images to test duplicate detection
api = ImageIndexAPI()

test_paths = [
    "/mnt/music/home/joe/images/coco_train2017/train2017/000000097989.jpg",
    "/mnt/music/home/joe/images/coco_train2017/train2017/000000563475.jpg"
]

result = api.add_images(test_paths)
print(result)
# Should show: already_indexed_count=2, new_images_count=0
```

### 3. Test with New Images

Create test images and submit:

```python
# Your application creates or detects new images
new_test_paths = [
    "/mnt/music/home/joe/images/test_batch/new_img1.jpg",
    "/mnt/music/home/joe/images/test_batch/new_img2.jpg"
]

result = api.add_images(new_test_paths)
# Should get a real job_id

# Monitor to completion
final = api.wait_for_job(result["job_id"])
print(final)
```

## Support and Troubleshooting

### API Not Responding

```bash
# Check if API is running on duc17
ssh root@duc17-40g.eng.qumulo.com "ps aux | grep api_server"

# Check API logs
ssh root@duc17-40g.eng.qumulo.com "tail -f /root/ImageRecognition/api_server.log"
```

### Job Stuck in "queued" Status

This means the background worker is not processing. Check API server logs.

### Images Not Being Indexed

1. Verify paths are correct (absolute, on NFS mount)
2. Check that image files exist and are readable
3. Check job status for error messages

### Getting Wrong Total Image Count

The API reads from the actual index metadata file. If counts seem wrong:

```bash
# Check index metadata directly
cat /mnt/music/home/joe/imageindex.meta.json
```

## Complete Example Application

Here's a complete example showing a typical integration:

```python
#!/usr/bin/env python3
"""
Example: Image monitoring application that integrates with the API.

This application:
1. Watches a directory for new images
2. Submits them to the indexing API
3. Monitors progress
4. Reports statistics
"""

import time
from pathlib import Path
from typing import List
import requests


class ImageIndexAPI:
    """API client (see implementation above)."""
    # ... (same as before)


class ImageMonitor:
    """Monitors directory for new images and submits to API."""

    def __init__(self, watch_dir: str, api: ImageIndexAPI):
        self.watch_dir = Path(watch_dir)
        self.api = api
        self.processed_images = set()

    def find_new_images(self) -> List[str]:
        """Find images that haven't been processed yet."""
        new_images = []

        for ext in ['*.jpg', '*.jpeg', '*.png']:
            for img_path in self.watch_dir.rglob(ext):
                path_str = str(img_path.absolute())

                if path_str not in self.processed_images:
                    new_images.append(path_str)

        return new_images

    def process_batch(self, image_paths: List[str]):
        """Submit batch to API and monitor."""
        print(f"Processing {len(image_paths)} images...")

        # Translate to NFS paths if needed
        nfs_paths = [self.translate_to_nfs(p) for p in image_paths]

        # Submit to API
        result = self.api.add_images(nfs_paths)

        if result["job_id"] == "none":
            print("All images already indexed")
            self.processed_images.update(image_paths)
            return

        print(f"Job {result['job_id']}: {result['new_images_count']} new images")

        # Monitor progress
        def show_progress(progress):
            print(f"  {progress['percent_complete']:.1f}% complete")

        final = self.api.wait_for_job(
            result["job_id"],
            progress_callback=show_progress
        )

        if final["status"] == "completed":
            print(f"Completed! Processed {final['progress']['processed_images']}")
            self.processed_images.update(image_paths)
        else:
            print(f"Failed: {final['error_message']}")

    def translate_to_nfs(self, path: str) -> str:
        """Translate local path to NFS path."""
        # Example: /local/images/... -> /mnt/music/home/joe/images/...
        # Adjust based on your setup
        return path.replace("/local/images", "/mnt/music/home/joe/images")

    def run(self, interval: int = 60):
        """Run continuous monitoring."""
        print(f"Monitoring {self.watch_dir} every {interval} seconds...")

        while True:
            try:
                new_images = self.find_new_images()

                if new_images:
                    self.process_batch(new_images)
                else:
                    print("No new images")

                # Show current stats
                stats = self.api.get_index_stats()
                print(f"Index total: {stats['total_images']} images")

            except Exception as e:
                print(f"Error: {e}")

            time.sleep(interval)


def main():
    api = ImageIndexAPI()
    monitor = ImageMonitor("/path/to/watch", api)
    monitor.run(interval=60)


if __name__ == "__main__":
    main()
```

## Summary

To integrate with the Image Indexing API:

1. **Make HTTP POST requests** to `/api/v1/index/add-images` with new image paths
2. **Poll the job status** endpoint to monitor progress
3. **Query statistics** endpoint to get total images in index
4. **Use absolute NFS paths** for all image file paths
5. **Handle the case** where images are already indexed (job_id="none")
6. **Implement error handling** for network and API errors

The API handles duplicate detection automatically, so you can safely submit the same images multiple times without re-indexing them.
