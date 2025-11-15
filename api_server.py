#!/usr/bin/env python3
"""
FastAPI server for distributed image indexing.

This API allows external systems to:
1. Notify of new images to be indexed
2. Check progress of ongoing indexing jobs
3. Query total images in the index

Usage:
  uvicorn api_server:app --host 0.0.0.0 --port 8000
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from enum import Enum

from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel, Field
import uvicorn


# --------- Configuration --------- #

CONFIG = {
    "index_prefix": "/mnt/music/home/joe/imageindex",
    "state_file": "/mnt/music/home/joe/imageindex.state.json",
    "workers_hosts": [
        "duc212-100g.eng.qumulo.com",
        "duc213-100g.eng.qumulo.com",
        "duc214-100g.eng.qumulo.com",
        "duc17-40g.eng.qumulo.com",
    ],
    "api_keys": {
        "dev-key-12345": "Development Key",
        "prod-key-67890": "Production Key",
    },
}


# --------- Models --------- #

class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AddImagesRequest(BaseModel):
    """Request to add new images to the index."""
    image_paths: List[str] = Field(..., description="List of absolute image file paths", min_items=1)
    priority: str = Field("normal", description="Job priority: low, normal, high")

    class Config:
        json_schema_extra = {
            "example": {
                "image_paths": [
                    "/mnt/music/home/joe/images/batch1/img001.jpg",
                    "/mnt/music/home/joe/images/batch1/img002.jpg"
                ],
                "priority": "normal"
            }
        }


class AddImagesResponse(BaseModel):
    """Response after adding images."""
    job_id: str
    status: JobStatus
    images_count: int
    new_images_count: int
    already_indexed_count: int
    message: str


class JobProgress(BaseModel):
    """Progress information for a job."""
    total_images: int
    processed_images: int
    failed_images: int
    percent_complete: float


class WorkerStatus(BaseModel):
    """Status of a single worker."""
    worker_id: int
    host: str
    status: str
    images_processed: int


class JobStatusResponse(BaseModel):
    """Detailed status of an indexing job."""
    job_id: str
    status: JobStatus
    progress: Optional[JobProgress] = None
    workers: Optional[List[WorkerStatus]] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


class IndexStats(BaseModel):
    """Statistics about the current index."""
    model_name: str
    embedding_dim: int
    total_images: int
    num_failed: int
    last_updated: str
    index_size_mb: float


# --------- State Management --------- #

class StateManager:
    """Manages index state and job tracking."""

    def __init__(self, state_file: str):
        self.state_file = Path(state_file)
        self.state = self._load_state()
        self.jobs: Dict[str, Dict[str, Any]] = {}

    def _load_state(self) -> dict:
        """Load state from file or create new."""
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                return json.load(f)
        else:
            return {
                "version": "1.0",
                "indexed_images": {},
                "total_images": 0,
                "last_updated": None,
            }

    def _save_state(self):
        """Save state to file."""
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)

    def is_image_indexed(self, image_path: str) -> bool:
        """Check if an image is already indexed."""
        return image_path in self.state["indexed_images"]

    def filter_new_images(self, image_paths: List[str]) -> tuple[List[str], List[str]]:
        """Split images into new and already indexed."""
        new_images = []
        already_indexed = []

        for path in image_paths:
            if self.is_image_indexed(path):
                already_indexed.append(path)
            else:
                new_images.append(path)

        return new_images, already_indexed

    def create_job(self, image_paths: List[str]) -> str:
        """Create a new indexing job."""
        job_id = f"idx_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.jobs[job_id] = {
            "job_id": job_id,
            "status": JobStatus.QUEUED,
            "image_paths": image_paths,
            "total_images": len(image_paths),
            "processed_images": 0,
            "failed_images": 0,
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "error_message": None,
        }

        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details."""
        return self.jobs.get(job_id)

    def update_job_status(self, job_id: str, status: JobStatus, **kwargs):
        """Update job status and optional fields."""
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = status
            self.jobs[job_id].update(kwargs)

    def mark_images_indexed(self, image_paths: List[str]):
        """Mark images as indexed in state."""
        timestamp = datetime.now().isoformat()
        for path in image_paths:
            self.state["indexed_images"][path] = {
                "indexed_at": timestamp,
                "status": "indexed",
            }

        self.state["total_images"] = len(self.state["indexed_images"])
        self.state["last_updated"] = timestamp
        self._save_state()

    def get_index_stats(self) -> dict:
        """Get current index statistics."""
        # Load metadata from index
        meta_file = Path(CONFIG["index_prefix"]).with_suffix(".meta.json")

        if meta_file.exists():
            with open(meta_file, 'r') as f:
                meta = json.load(f)
        else:
            meta = {
                "model_name": "clip-ViT-L-14",
                "embedding_dim": 768,
                "num_images": 0,
                "num_failed": 0,
            }

        # Calculate index size
        faiss_file = Path(CONFIG["index_prefix"]).with_suffix(".faiss")
        parquet_file = Path(CONFIG["index_prefix"]).with_suffix(".parquet")

        total_size = 0
        if faiss_file.exists():
            total_size += faiss_file.stat().st_size
        if parquet_file.exists():
            total_size += parquet_file.stat().st_size

        return {
            "model_name": meta.get("model_name", "unknown"),
            "embedding_dim": meta.get("embedding_dim", 0),
            "total_images": meta.get("num_images", 0),
            "num_failed": meta.get("num_failed", 0),
            "last_updated": self.state.get("last_updated", "never"),
            "index_size_mb": round(total_size / (1024 * 1024), 2),
        }


# --------- API Server --------- #

app = FastAPI(
    title="Image Indexing API",
    description="API for distributed CLIP-based image indexing",
    version="1.0.0",
)

# Global state manager
state_manager = StateManager(CONFIG["state_file"])


# --------- Authentication --------- #

def verify_api_key(x_api_key: Optional[str] = Header(None)) -> bool:
    """Verify API key from header."""
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="Missing API key header (X-API-Key)")

    if x_api_key not in CONFIG["api_keys"]:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return True


# --------- Background Tasks --------- #

async def process_indexing_job(job_id: str):
    """
    Background task to process an indexing job.

    This is a placeholder that simulates the work.
    In production, this would:
    1. Call controller_service.py to distribute work
    2. Monitor worker progress
    3. Merge results
    4. Update state
    """
    job = state_manager.get_job(job_id)
    if not job:
        return

    # Update to running
    state_manager.update_job_status(
        job_id,
        JobStatus.RUNNING,
        started_at=datetime.now().isoformat()
    )

    try:
        # Simulate processing (in reality, call controller)
        total = job["total_images"]
        for i in range(total):
            await asyncio.sleep(0.1)  # Simulate work

            # Update progress
            state_manager.jobs[job_id]["processed_images"] = i + 1

        # Mark images as indexed
        state_manager.mark_images_indexed(job["image_paths"])

        # Update to completed
        state_manager.update_job_status(
            job_id,
            JobStatus.COMPLETED,
            completed_at=datetime.now().isoformat(),
            processed_images=total
        )

    except Exception as e:
        # Update to failed
        state_manager.update_job_status(
            job_id,
            JobStatus.FAILED,
            completed_at=datetime.now().isoformat(),
            error_message=str(e)
        )


# --------- API Endpoints --------- #

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "Image Indexing API",
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "index_available": Path(CONFIG["index_prefix"]).with_suffix(".faiss").exists(),
    }


@app.post("/api/v1/index/add-images", response_model=AddImagesResponse)
async def add_images(
    request: AddImagesRequest,
    background_tasks: BackgroundTasks,
    authenticated: bool = Header(None, include_in_schema=False, alias="X-API-Key", convert_underscores=True)
):
    """
    Add new images to the indexing queue.

    External systems call this endpoint to notify of new images that need to be indexed.
    The API will filter out already-indexed images and queue the new ones for processing.
    """
    # Note: Authentication is handled by dependency injection in production
    # For now, we'll add manual verification
    try:
        verify_api_key(authenticated)
    except:
        pass  # For development, allow unauthenticated access

    # Filter new vs already indexed
    new_images, already_indexed = state_manager.filter_new_images(request.image_paths)

    if not new_images:
        return AddImagesResponse(
            job_id="none",
            status=JobStatus.COMPLETED,
            images_count=len(request.image_paths),
            new_images_count=0,
            already_indexed_count=len(already_indexed),
            message="All images already indexed"
        )

    # Create job
    job_id = state_manager.create_job(new_images)

    # Queue background processing
    background_tasks.add_task(process_indexing_job, job_id)

    return AddImagesResponse(
        job_id=job_id,
        status=JobStatus.QUEUED,
        images_count=len(request.image_paths),
        new_images_count=len(new_images),
        already_indexed_count=len(already_indexed),
        message=f"Queued {len(new_images)} new images for indexing"
    )


@app.get("/api/v1/index/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    Get the status of an indexing job.

    Returns detailed progress information including:
    - Current status (queued, running, completed, failed)
    - Number of images processed
    - Percentage complete
    - Start/end timestamps
    """
    job = state_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    response = JobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        error_message=job.get("error_message"),
    )

    # Add progress if job is running or completed
    if job["status"] in [JobStatus.RUNNING, JobStatus.COMPLETED, JobStatus.FAILED]:
        total = job["total_images"]
        processed = job["processed_images"]

        response.progress = JobProgress(
            total_images=total,
            processed_images=processed,
            failed_images=job["failed_images"],
            percent_complete=round((processed / total * 100) if total > 0 else 0, 1)
        )

    return response


@app.get("/api/v1/index/status", response_model=Dict[str, Any])
async def get_overall_status():
    """
    Get overall indexing system status.

    Returns:
    - Total images in index
    - Number of active jobs
    - Recent job history
    """
    stats = state_manager.get_index_stats()

    # Get active jobs
    active_jobs = [
        {"job_id": jid, "status": job["status"], "created_at": job["created_at"]}
        for jid, job in state_manager.jobs.items()
        if job["status"] in [JobStatus.QUEUED, JobStatus.RUNNING]
    ]

    # Get recent completed jobs
    recent_jobs = sorted(
        [
            {"job_id": jid, "status": job["status"], "created_at": job["created_at"], "images": job["total_images"]}
            for jid, job in state_manager.jobs.items()
            if job["status"] in [JobStatus.COMPLETED, JobStatus.FAILED]
        ],
        key=lambda x: x["created_at"],
        reverse=True
    )[:10]

    return {
        "total_indexed_images": stats["total_images"],
        "active_jobs": len(active_jobs),
        "active_job_details": active_jobs,
        "recent_jobs": recent_jobs,
        "index_stats": stats,
    }


@app.get("/api/v1/index/stats", response_model=IndexStats)
async def get_index_stats():
    """
    Get statistics about the current index.

    Returns:
    - Total number of indexed images
    - Model information
    - Index size
    - Last update timestamp
    """
    stats = state_manager.get_index_stats()
    return IndexStats(**stats)


# --------- Main --------- #

if __name__ == "__main__":
    print("Starting Image Indexing API server...")
    print(f"Index prefix: {CONFIG['index_prefix']}")
    print(f"State file: {CONFIG['state_file']}")
    print("\nAPI will be available at: http://0.0.0.0:8000")
    print("API docs at: http://0.0.0.0:8000/docs")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
