#!/bin/bash
#
# Automatically extract COCO dataset and start indexing once download completes
#
# Usage:
#   ./auto_index_coco.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOWNLOAD_HOST="duc17-40g.eng.qumulo.com"
REMOTE_COCO_DIR="/mnt/music/home/joe/images/coco_train2017"
REMOTE_ZIP="${REMOTE_COCO_DIR}/train2017.zip"
LOCAL_IMAGE_DIR="/Volumes/files/home/joe/images"
LOCAL_INDEX_PREFIX="/Volumes/files/home/joe/imageindex"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[AUTO-INDEX]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[AUTO-INDEX]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[AUTO-INDEX]${NC} $1"
}

log_error() {
    echo -e "${RED}[AUTO-INDEX]${NC} $1"
}

# Monitor download progress
log "Monitoring COCO train2017 download on ${DOWNLOAD_HOST}..."
log "This may take 15-20 minutes depending on connection speed"
echo

EXPECTED_SIZE=$((18 * 1024 * 1024 * 1024))  # ~18GB in bytes
TOLERANCE=$((100 * 1024 * 1024))  # 100MB tolerance

while true; do
    # Check if file exists and get size
    CURRENT_SIZE=$(ssh root@"${DOWNLOAD_HOST}" "stat -c %s ${REMOTE_ZIP} 2>/dev/null || echo 0")

    if [ "$CURRENT_SIZE" -eq 0 ]; then
        log_warn "Download not started or file not found yet, waiting..."
        sleep 30
        continue
    fi

    # Calculate progress
    CURRENT_GB=$(echo "scale=2; $CURRENT_SIZE / 1024 / 1024 / 1024" | bc)
    PERCENT=$(echo "scale=1; $CURRENT_SIZE * 100 / $EXPECTED_SIZE" | bc)

    log "Download progress: ${CURRENT_GB} GB (${PERCENT}%)"

    # Check if download is complete (size stable for 30 seconds)
    sleep 30
    NEW_SIZE=$(ssh root@"${DOWNLOAD_HOST}" "stat -c %s ${REMOTE_ZIP} 2>/dev/null || echo 0")

    if [ "$NEW_SIZE" -eq "$CURRENT_SIZE" ] && [ "$NEW_SIZE" -gt $((EXPECTED_SIZE - TOLERANCE)) ]; then
        log_success "Download complete! File size: ${CURRENT_GB} GB"
        break
    fi
done

# Extract the zip file
log ""
log "=========================================="
log "Extracting COCO dataset..."
log "=========================================="

ssh root@"${DOWNLOAD_HOST}" "cd ${REMOTE_COCO_DIR} && unzip -q train2017.zip && rm train2017.zip"

if [ $? -ne 0 ]; then
    log_error "Failed to extract COCO dataset"
    exit 1
fi

# Count extracted images
NUM_IMAGES=$(ssh root@"${DOWNLOAD_HOST}" "find ${REMOTE_COCO_DIR}/train2017 -type f \( -name '*.jpg' -o -name '*.png' \) | wc -l")
log_success "Extracted ${NUM_IMAGES} images"

# Start indexing
log ""
log "=========================================="
log "Starting distributed indexing..."
log "=========================================="
log "This will take significant time with ~118k images"
log "Estimated time: 2-4 hours depending on hardware"
echo

cd "${SCRIPT_DIR}"

python3 controller.py \
    --image-dir "${LOCAL_IMAGE_DIR}" \
    --index-prefix "${LOCAL_INDEX_PREFIX}"

if [ $? -ne 0 ]; then
    log_error "Indexing failed"
    exit 1
fi

log ""
log "=========================================="
log_success "COMPLETE! COCO dataset indexed successfully"
log "=========================================="
log "You can now run queries against ~118k images:"
log "  python3 query_client.py --query 'people walking in a park'"
log ""
