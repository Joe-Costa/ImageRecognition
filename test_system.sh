#!/bin/bash
#
# Quick test script for the distributed indexing system
#
# Usage:
#   ./test_system.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[TEST]${NC} $1"
}

log_info() {
    echo -e "${YELLOW}[TEST]${NC} $1"
}

echo "========================================"
echo "Distributed Image Indexing - System Test"
echo "========================================"
echo

# Test 1: Check if hosts file exists
log "Checking hosts file..."
if [ ! -f "$SCRIPT_DIR/hosts" ]; then
    echo "ERROR: hosts file not found"
    exit 1
fi
log_success "hosts file found"

# Test 2: Check if all scripts exist
log "Checking scripts..."
scripts=("controller.py" "worker_index.py" "merge_indexes.py" "setup_workers.sh")
for script in "${scripts[@]}"; do
    if [ ! -f "$SCRIPT_DIR/$script" ]; then
        echo "ERROR: $script not found"
        exit 1
    fi
done
log_success "All scripts found"

# Test 3: Check Python version
log "Checking Python version..."
python_version=$(python3 --version 2>&1)
log_info "$python_version"

# Test 4: Check if required Python packages are installed (local)
log "Checking local Python packages..."
python3 -c "
import sys
packages = ['sentence_transformers', 'faiss', 'polars', 'PIL', 'numpy']
missing = []
for pkg in packages:
    try:
        __import__(pkg if pkg != 'PIL' else 'PIL')
    except ImportError:
        missing.append(pkg)

if missing:
    print(f'Missing packages: {', '.join(missing)}')
    print('Run: pip install -r requirements.txt')
    sys.exit(1)
else:
    print('All packages installed')
" || {
    log_info "Install packages with: pip install -r requirements.txt"
    exit 1
}
log_success "All packages installed locally"

# Test 5: Check SSH connectivity to all hosts
log "Testing SSH connectivity to workers..."
mapfile -t HOSTS < <(grep -v '^#' "$SCRIPT_DIR/hosts" | grep -v '^[[:space:]]*$')

ssh_ok=true
for host in "${HOSTS[@]}"; do
    log "  Testing $host..."
    if ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@"$host" "echo 'OK'" > /dev/null 2>&1; then
        log_success "    $host: SSH OK"
    else
        echo "    ERROR: Cannot SSH to $host"
        ssh_ok=false
    fi
done

if [ "$ssh_ok" = false ]; then
    echo "ERROR: SSH connectivity issues detected"
    exit 1
fi

# Test 6: Check NFS mount on workers
log "Checking NFS mounts on workers..."
for host in "${HOSTS[@]}"; do
    log "  Checking $host..."
    if ssh root@"$host" "test -d /mnt/music/home/joe && echo 'OK'" 2>/dev/null | grep -q "OK"; then
        log_success "    $host: NFS mount OK"
    else
        echo "    ERROR: NFS mount not accessible on $host"
        exit 1
    fi
done

# Test 7: Check local SMB mount
log "Checking local SMB mount..."
if [ ! -d "/Volumes/home/joe" ]; then
    echo "ERROR: Local SMB mount /Volumes/home/joe not found"
    exit 1
fi
log_success "Local SMB mount OK"

# Test 8: Check if image directory exists
log "Checking image directory..."
if [ ! -d "/Volumes/home/joe/images" ]; then
    log_info "Image directory /Volumes/home/joe/images not found"
    log_info "You may need to create it or adjust the path"
else
    image_count=$(find /Volumes/home/joe/images -type f \( -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" \) 2>/dev/null | wc -l)
    log_success "Image directory exists with ~$image_count images"
fi

echo
echo "========================================"
log_success "All system tests passed!"
echo "========================================"
echo
log_info "Next steps:"
echo "  1. If workers not set up: ./setup_workers.sh"
echo "  2. Run indexing: python3 controller.py --image-dir /Volumes/home/joe/images --index-prefix /Volumes/home/joe/imageindex"
echo "  3. Query index: python3 images_search.py query --index-prefix /Volumes/home/joe/imageindex --text 'your query'"
echo
