#!/usr/bin/env python3
"""
Test client for the Image Indexing API.

Demonstrates how external systems can interact with the API to:
1. Submit new images for indexing
2. Check progress of indexing jobs
3. Get statistics about the index

Usage:
  python3 test_api_client.py
"""

import requests
import time
from typing import List


class ImageIndexClient:
    """Client for interacting with the Image Indexing API."""

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers["X-API-Key"] = api_key

    def add_images(self, image_paths: List[str], priority: str = "normal") -> dict:
        """Submit new images for indexing."""
        response = requests.post(
            f"{self.base_url}/api/v1/index/add-images",
            json={
                "image_paths": image_paths,
                "priority": priority
            },
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_job_status(self, job_id: str) -> dict:
        """Get status of a specific indexing job."""
        response = requests.get(
            f"{self.base_url}/api/v1/index/status/{job_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_overall_status(self) -> dict:
        """Get overall system status."""
        response = requests.get(
            f"{self.base_url}/api/v1/index/status",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_index_stats(self) -> dict:
        """Get index statistics."""
        response = requests.get(
            f"{self.base_url}/api/v1/index/stats",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def wait_for_job(self, job_id: str, poll_interval: int = 5, timeout: int = 600) -> dict:
        """
        Wait for a job to complete.

        Args:
            job_id: The job ID to monitor
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait

        Returns:
            Final job status
        """
        start_time = time.time()

        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")

            status = self.get_job_status(job_id)

            if status["status"] in ["completed", "failed"]:
                return status

            if status.get("progress"):
                print(f"  Progress: {status['progress']['percent_complete']}% "
                      f"({status['progress']['processed_images']}/{status['progress']['total_images']})")

            time.sleep(poll_interval)


def main():
    """Example usage of the API client."""

    print("=" * 60)
    print("Image Indexing API - Test Client")
    print("=" * 60)

    # Initialize client
    client = ImageIndexClient(base_url="http://localhost:8000")

    # 1. Get current index stats
    print("\n1. Getting current index statistics...")
    stats = client.get_index_stats()
    print(f"   Model: {stats['model_name']}")
    print(f"   Total images: {stats['total_images']}")
    print(f"   Index size: {stats['index_size_mb']} MB")
    print(f"   Last updated: {stats['last_updated']}")

    # 2. Submit new images for indexing
    print("\n2. Submitting new images for indexing...")

    test_images = [
        "/mnt/music/home/joe/images/test/image1.jpg",
        "/mnt/music/home/joe/images/test/image2.jpg",
        "/mnt/music/home/joe/images/test/image3.jpg",
    ]

    result = client.add_images(test_images)
    print(f"   Job ID: {result['job_id']}")
    print(f"   Status: {result['status']}")
    print(f"   New images: {result['new_images_count']}")
    print(f"   Already indexed: {result['already_indexed_count']}")

    if result['job_id'] == "none":
        print("   All images already indexed, no job created")
        return

    job_id = result['job_id']

    # 3. Monitor job progress
    print(f"\n3. Monitoring job {job_id}...")

    try:
        final_status = client.wait_for_job(job_id, poll_interval=2)
        print(f"   Final status: {final_status['status']}")

        if final_status.get('progress'):
            print(f"   Processed: {final_status['progress']['processed_images']}")
            print(f"   Failed: {final_status['progress']['failed_images']}")

    except TimeoutError as e:
        print(f"   ERROR: {e}")

    # 4. Get overall system status
    print("\n4. Getting overall system status...")
    overall = client.get_overall_status()
    print(f"   Total indexed images: {overall['total_indexed_images']}")
    print(f"   Active jobs: {overall['active_jobs']}")

    if overall['recent_jobs']:
        print(f"   Recent jobs:")
        for job in overall['recent_jobs'][:3]:
            print(f"     - {job['job_id']}: {job['status']} ({job['images']} images)")

    # 5. Get updated index stats
    print("\n5. Getting updated index statistics...")
    stats = client.get_index_stats()
    print(f"   Total images: {stats['total_images']}")
    print(f"   Index size: {stats['index_size_mb']} MB")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
