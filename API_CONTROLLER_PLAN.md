# API Endpoint and Controller Migration Plan

## Executive Summary

Transform duc17-40g from a worker node into the primary controller and API endpoint for the distributed image indexing system. This architectural change will:

1. **Centralize control** - Move orchestration from Mac client to duc17
2. **Enable automation** - Allow external systems to trigger indexing via REST API
3. **Support incremental indexing** - Process new images without full re-indexing
4. **Improve reliability** - Eliminate dependency on Mac client being available

---

## Current Architecture Analysis

### Current Components

**Mac Client Side:**
- `controller.py` - Orchestrates distributed work, manages SSH connections
- `query_client.py` - Submits queries to workers via SSH
- `merge_client.py` - Triggers merge operations via SSH
- `auto_index_coco.sh` - Automation wrapper for download/extract/index

**Worker Nodes (duc212, duc213, duc214, duc17):**
- `worker_index.py` - Processes assigned image chunks
- `remote_query.py` - Executes search queries
- `merge_indexes.py` - Combines partial indexes
- Python venv with CLIP, Faiss, Polars dependencies

### Current Workflow

1. Mac client scans for images locally
2. Mac translates paths to NFS mount paths
3. Mac distributes work to 4 workers via SSH
4. Workers process independently
5. Mac monitors worker completion
6. Mac triggers merge operation on duc17
7. Merged index ready for queries

### Pain Points

- **Mac dependency** - Client must be running for batch jobs
- **No API** - Cannot trigger indexing programmatically
- **Manual triggers** - Requires human intervention
- **Full re-index** - Adding new images requires re-processing everything
- **SSH overhead** - Mac orchestrating via SSH adds latency

---

## Proposed Architecture

### New Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         duc17-40g                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              API Server (FastAPI/Flask)                │ │
│  │  POST /api/index/trigger                               │ │
│  │  POST /api/index/notify (new images)                   │ │
│  │  GET  /api/index/status                                │ │
│  │  POST /api/query                                       │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           Controller Service (controller.py)           │ │
│  │  - Work distribution                                   │ │
│  │  - Worker monitoring                                   │ │
│  │  - Merge orchestration                                 │ │
│  │  - Incremental index updates                           │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Query Service (remote_query.py)           │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ SSH Commands
                           ▼
        ┌──────────────────────────────────────┐
        │     Worker Nodes (duc212-214)        │
        │  - worker_index.py (process images)  │
        └──────────────────────────────────────┘
```

### Component Migration

**New Components on duc17:**

1. **API Server** (`api_server.py`)
   - REST API endpoints for external integrations
   - Background job queue management
   - Authentication/authorization
   - Request validation

2. **Controller Service** (enhanced `controller.py`)
   - Now runs on duc17 instead of Mac
   - Manages distributed workers
   - Tracks indexing state
   - Handles incremental updates

3. **Indexing State Tracker** (`index_state.py`)
   - Tracks which images are indexed
   - Identifies new/changed images
   - Maintains processing queue
   - Stores metadata in SQLite/JSON

4. **Background Worker** (`job_worker.py`)
   - Processes API requests asynchronously
   - Manages long-running indexing jobs
   - Updates job status
   - Sends notifications on completion

**Modified Components:**

- `worker_index.py` - No changes needed
- `remote_query.py` - Integrate with API
- `merge_indexes.py` - Add incremental merge support

**Deprecated Components:**

- `query_client.py` - Replaced by API calls
- `merge_client.py` - Replaced by controller on duc17
- `auto_index_coco.sh` - Replaced by API trigger

---

## API Design

### Endpoints

#### 1. Trigger Full Index

```http
POST /api/v1/index/trigger
Content-Type: application/json

{
  "image_dir": "/mnt/music/home/joe/images",
  "index_prefix": "/mnt/music/home/joe/imageindex",
  "force_reindex": false
}

Response: 202 Accepted
{
  "job_id": "idx_20251114_123456",
  "status": "queued",
  "message": "Indexing job queued for processing"
}
```

#### 2. Notify New Images Available

```http
POST /api/v1/index/notify
Content-Type: application/json

{
  "image_paths": [
    "/mnt/music/home/joe/images/new_batch/img001.jpg",
    "/mnt/music/home/joe/images/new_batch/img002.jpg"
  ],
  "priority": "normal"
}

Response: 202 Accepted
{
  "job_id": "idx_20251114_123457",
  "status": "queued",
  "images_count": 2,
  "estimated_time_seconds": 120
}
```

#### 3. Check Job Status

```http
GET /api/v1/index/status/{job_id}

Response: 200 OK
{
  "job_id": "idx_20251114_123456",
  "status": "running",
  "progress": {
    "total_images": 1000,
    "processed_images": 437,
    "failed_images": 2,
    "percent_complete": 43.7
  },
  "workers": [
    {"worker_id": 0, "status": "running", "images_processed": 109},
    {"worker_id": 1, "status": "running", "images_processed": 108},
    {"worker_id": 2, "status": "running", "images_processed": 110},
    {"worker_id": 3, "status": "running", "images_processed": 110}
  ],
  "started_at": "2025-11-14T12:34:56Z",
  "estimated_completion": "2025-11-14T13:15:00Z"
}
```

#### 4. List All Jobs

```http
GET /api/v1/index/jobs?status=running&limit=10

Response: 200 OK
{
  "jobs": [
    {
      "job_id": "idx_20251114_123456",
      "status": "running",
      "created_at": "2025-11-14T12:34:56Z",
      "images_count": 1000
    }
  ],
  "total": 1
}
```

#### 5. Submit Query

```http
POST /api/v1/query
Content-Type: application/json

{
  "text": "dogs playing in a park",
  "top_k": 10,
  "copy_results": false
}

Response: 200 OK
{
  "query": "dogs playing in a park",
  "results": [
    {
      "rank": 1,
      "score": 0.2856,
      "image_path": "/mnt/music/home/joe/images/coco_train2017/train2017/000000025148.jpg"
    },
    ...
  ],
  "query_time_seconds": 12.85,
  "index_stats": {
    "total_images": 118323,
    "model": "clip-ViT-L-14"
  }
}
```

#### 6. Get Index Stats

```http
GET /api/v1/index/stats

Response: 200 OK
{
  "model_name": "clip-ViT-L-14",
  "embedding_dim": 768,
  "num_images": 118323,
  "num_failed": 0,
  "last_updated": "2025-11-14T08:05:00Z",
  "index_size_bytes": {
    "faiss": 363855872,
    "parquet": 411041792,
    "total": 774897664
  }
}
```

---

## Incremental Indexing Design

### State Tracking

**Index State File** (`/mnt/music/home/joe/imageindex.state.json`):

```json
{
  "version": "1.0",
  "last_full_index": "2025-11-14T08:05:00Z",
  "total_images": 118323,
  "indexed_images": {
    "/mnt/music/home/joe/images/coco_train2017/train2017/000000097989.jpg": {
      "indexed_at": "2025-11-14T08:05:00Z",
      "file_mtime": 1731585600,
      "file_size": 245632,
      "index_position": 0
    }
  },
  "pending_queue": [],
  "failed_images": []
}
```

### Incremental Update Workflow

1. **Detect New Images**
   - API receives notification with image paths
   - Controller checks state file for existing entries
   - Identifies truly new images (not in state)

2. **Create Incremental Batch**
   - Generate embeddings for new images only
   - Assign to single worker (duc17) for small batches
   - Distribute to all workers for large batches (>1000 images)

3. **Merge Strategy**

   **Option A: Append to Existing Index (Fast)**
   - Add new vectors to existing Faiss index using `index.add()`
   - Append new rows to Parquet file
   - Update state file
   - **Pros**: Very fast (seconds)
   - **Cons**: Index may become fragmented over time

   **Option B: Periodic Full Rebuild**
   - Maintain separate "delta" index for new images
   - Query both main + delta indexes
   - Merge results
   - Rebuild main index nightly/weekly
   - **Pros**: Maintains optimal index structure
   - **Cons**: Queries slightly slower (two searches)

4. **Update State**
   - Record new images in state file
   - Update metadata (total count, timestamp)
   - Maintain index position mapping

### Recommended Approach

**Hybrid Strategy:**
- Use append (Option A) for small batches (<5000 images)
- Trigger full rebuild when:
  - Delta size exceeds 10% of main index
  - On user request
  - Scheduled weekly maintenance window

---

## Implementation Plan

### Phase 1: API Server Foundation (Week 1)

**Tasks:**
1. Create FastAPI application structure
2. Implement basic endpoints (trigger, status, stats)
3. Add job queue using Redis or in-memory queue
4. Implement authentication (API keys)
5. Add request validation and error handling
6. Write unit tests for API layer

**Deliverables:**
- `api_server.py` - FastAPI application
- `api_models.py` - Pydantic models for requests/responses
- `job_queue.py` - Job queue management
- `auth.py` - API authentication
- Basic API documentation (OpenAPI/Swagger)

### Phase 2: Controller Migration (Week 2)

**Tasks:**
1. Refactor `controller.py` to run on duc17
2. Remove Mac-specific path handling
3. Add job status tracking
4. Integrate with API job queue
5. Add monitoring and logging
6. Test distributed worker coordination

**Deliverables:**
- `controller_service.py` - Enhanced controller
- `worker_monitor.py` - Worker health checks
- Integration with API endpoints

### Phase 3: State Tracking & Incremental Indexing (Week 2-3)

**Tasks:**
1. Design and implement state tracking system
2. Create index state file format
3. Implement image change detection
4. Add incremental update logic
5. Implement append-to-index functionality
6. Add delta index support
7. Create rebuild scheduling

**Deliverables:**
- `index_state.py` - State management
- `incremental_indexer.py` - Incremental update logic
- `merge_strategy.py` - Merge decision engine

### Phase 4: Query Integration (Week 3)

**Tasks:**
1. Integrate `remote_query.py` with API
2. Add support for querying delta indexes
3. Implement result merging from multiple indexes
4. Add caching for repeated queries
5. Optimize query performance

**Deliverables:**
- `query_service.py` - Query handling service
- API query endpoint
- Query result caching

### Phase 5: Background Jobs & Monitoring (Week 4)

**Tasks:**
1. Implement background job worker
2. Add job retry logic
3. Create monitoring dashboard
4. Add email/webhook notifications
5. Implement logging and metrics
6. Create admin endpoints

**Deliverables:**
- `job_worker.py` - Background job processor
- `notifications.py` - Alert system
- Monitoring dashboard
- Admin API endpoints

### Phase 6: Testing & Deployment (Week 4-5)

**Tasks:**
1. Integration testing
2. Load testing (concurrent jobs)
3. Failover testing
4. Documentation
5. Deployment automation
6. Migration from old system

**Deliverables:**
- Comprehensive test suite
- Deployment scripts
- User documentation
- Migration guide

---

## Technical Considerations

### Technology Stack

**API Server:**
- **Framework**: FastAPI (async, fast, auto-documentation)
- **Job Queue**: Redis with RQ or Celery (for production) OR simple in-memory queue (for MVP)
- **Authentication**: API key middleware
- **Validation**: Pydantic models
- **Logging**: Python logging to file + stdout

**State Management:**
- **State Storage**: JSON file (simple) OR SQLite (scalable)
- **Locking**: File locks for concurrent access
- **Backup**: Automated state file backups

**Monitoring:**
- **Metrics**: Prometheus-compatible metrics
- **Health Checks**: /health endpoint
- **Logging**: Structured JSON logs

### Scalability

**Current Scale:**
- 118k images indexed
- 4 workers
- ~25 hours for full index

**Expected Scale:**
- Up to 1M images
- 4 workers (current)
- Incremental updates: 1-1000 images per batch

**Performance Targets:**
- API response time: <100ms
- Small batch indexing (100 images): <2 minutes
- Large batch indexing (10k images): <2 hours
- Query response: <15 seconds

### High Availability

**Single Point of Failure: duc17**
- Current design has duc17 as controller
- Mitigation: State file on NFS (shared)
- Future: Add controller failover to duc212

**Recovery Strategy:**
- State file contains all indexing history
- Can resume interrupted jobs
- Automatic retry for failed images

### Security

**API Security:**
- API key authentication
- Rate limiting per key
- Request size limits
- Input validation

**Network Security:**
- Firewall rules (restrict to internal network)
- HTTPS for production
- SSH key-based worker communication

**Data Security:**
- No sensitive data in logs
- State file permissions (0600)
- Secure API key storage

---

## Migration Strategy

### Parallel Run

1. **Keep existing system operational**
2. **Deploy new API on duc17**
3. **Test with small subset of images**
4. **Validate results match old system**
5. **Gradually increase load**
6. **Full cutover when confident**

### Rollback Plan

- Keep Mac client scripts available
- Maintain snapshot of current index
- Document rollback procedures
- Test rollback before cutover

### Data Migration

- No data migration needed (indexes stay in place)
- State file is new (generated from existing index)
- First run scans existing index to build state

---

## Success Criteria

### Functional Requirements

- [ ] API accepts new image notifications
- [ ] Incremental indexing adds new images without full re-index
- [ ] Query results identical to current system
- [ ] Job status tracking accurate
- [ ] Failed jobs automatically retried
- [ ] State persists across restarts

### Performance Requirements

- [ ] API responds in <100ms
- [ ] Small batch (100 images) completes in <5 minutes
- [ ] Query performance unchanged (<15 seconds)
- [ ] No downtime during incremental updates

### Operational Requirements

- [ ] API runs as systemd service
- [ ] Automatic restart on failure
- [ ] Logs accessible and searchable
- [ ] Monitoring dashboard available
- [ ] Documentation complete

---

## Open Questions

1. **Job Queue Technology**
   - Start with in-memory queue for MVP?
   - Or invest in Redis/Celery upfront?
   - **Recommendation**: Start simple (in-memory), add Redis later

2. **State Storage**
   - JSON file (simple, readable)?
   - SQLite (queryable, transactional)?
   - **Recommendation**: Start with JSON, migrate to SQLite if needed

3. **Merge Strategy**
   - Always append?
   - Separate delta index?
   - Scheduled rebuilds?
   - **Recommendation**: Append for MVP, add delta support later

4. **Authentication**
   - Simple API keys?
   - JWT tokens?
   - OAuth?
   - **Recommendation**: API keys for MVP (internal use)

5. **Monitoring**
   - Custom dashboard?
   - Grafana + Prometheus?
   - Simple logs?
   - **Recommendation**: Start with /status endpoint + logs, add Grafana later

6. **Deployment**
   - Manual deployment?
   - Systemd service?
   - Docker container?
   - **Recommendation**: Systemd service (native to Ubuntu)

---

## Next Steps

### Immediate Actions

1. **Review and approve this plan**
2. **Decide on open questions** (tech choices)
3. **Set up development environment on duc17**
4. **Create project structure**
5. **Start Phase 1 implementation**

### Week 1 Goals

- [ ] API server running on duc17
- [ ] Basic endpoints functional (trigger, status)
- [ ] Job queue working (in-memory)
- [ ] Can trigger manual index job via API
- [ ] API documentation available

### Questions for User

1. Do you want to start with a simple in-memory job queue or set up Redis immediately?
2. Should we prioritize incremental indexing or get the basic API working first?
3. What authentication method do you prefer (API keys, JWT, other)?
4. Do you want monitoring/metrics from day 1, or add later?
5. Any specific external systems that will call this API (helps inform design)?

---

## Appendix: File Structure

```
/root/ImageRecognition/
├── api/
│   ├── api_server.py          # FastAPI application
│   ├── api_models.py          # Pydantic request/response models
│   ├── auth.py                # Authentication middleware
│   └── routes/
│       ├── index.py           # Index management endpoints
│       ├── query.py           # Query endpoints
│       └── admin.py           # Admin endpoints
├── controller/
│   ├── controller_service.py # Main controller (migrated from Mac)
│   ├── worker_monitor.py     # Worker health checks
│   └── job_queue.py           # Job queue management
├── indexing/
│   ├── index_state.py         # State tracking
│   ├── incremental_indexer.py # Incremental updates
│   ├── merge_strategy.py      # Merge decision logic
│   └── worker_index.py        # Worker script (existing)
├── query/
│   ├── query_service.py       # Query handling
│   └── remote_query.py        # Query execution (existing)
├── common/
│   ├── config.py              # Configuration
│   ├── logging_config.py      # Logging setup
│   └── utils.py               # Shared utilities
├── scripts/
│   ├── start_api.sh           # API startup script
│   ├── deploy.sh              # Deployment automation
│   └── backup_state.sh        # State backup script
├── tests/
│   ├── test_api.py
│   ├── test_controller.py
│   └── test_incremental.py
└── requirements.txt           # Python dependencies
```

## Appendix: API Examples

### Example: Triggering Index from External System

```python
import requests

API_URL = "http://duc17-40g.eng.qumulo.com:8000"
API_KEY = "your-api-key-here"

headers = {"X-API-Key": API_KEY}

# Notify of new images
response = requests.post(
    f"{API_URL}/api/v1/index/notify",
    json={
        "image_paths": [
            "/mnt/music/home/joe/images/new_batch/img001.jpg",
            "/mnt/music/home/joe/images/new_batch/img002.jpg",
        ]
    },
    headers=headers
)

job_id = response.json()["job_id"]

# Poll for completion
import time
while True:
    status = requests.get(
        f"{API_URL}/api/v1/index/status/{job_id}",
        headers=headers
    ).json()

    if status["status"] == "completed":
        print("Indexing complete!")
        break
    elif status["status"] == "failed":
        print(f"Indexing failed: {status['error']}")
        break

    print(f"Progress: {status['progress']['percent_complete']}%")
    time.sleep(5)
```

### Example: Querying via API

```python
import requests

response = requests.post(
    f"{API_URL}/api/v1/query",
    json={
        "text": "people walking in a park",
        "top_k": 5
    },
    headers=headers
)

results = response.json()["results"]
for result in results:
    print(f"Rank {result['rank']}: {result['score']:.4f} - {result['image_path']}")
```
