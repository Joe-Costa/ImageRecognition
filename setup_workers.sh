#!/bin/bash
#
# Setup script for deploying dependencies to worker hosts.
#
# This script:
# 1. Checks connectivity to all workers
# 2. Verifies NFS mounts
# 3. Installs Python dependencies
# 4. Creates necessary directories
#
# Usage:
#   ./setup_workers.sh [hosts_file]
#

set -e  # Exit on error

HOSTS_FILE="${1:-./hosts}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

# Check if hosts file exists
if [ ! -f "$HOSTS_FILE" ]; then
    log_error "Hosts file not found: $HOSTS_FILE"
    exit 1
fi

# Read hosts from file (compatible with macOS bash)
HOSTS=()
while IFS= read -r line; do
    [[ -n "$line" && ! "$line" =~ ^# ]] && HOSTS+=("$line")
done < "$HOSTS_FILE"

if [ ${#HOSTS[@]} -eq 0 ]; then
    log_error "No hosts found in $HOSTS_FILE"
    exit 1
fi

log "Found ${#HOSTS[@]} worker hosts"
for host in "${HOSTS[@]}"; do
    log "  - $host"
done
echo

# Python packages to install
PACKAGES=(
    "sentence-transformers"
    "faiss-cpu"
    "polars"
    "pillow"
    "numpy"
)

# Function to setup a single worker
setup_worker() {
    local host=$1
    log "=========================================="
    log "Setting up worker: $host"
    log "=========================================="

    # Test SSH connectivity
    log "Testing SSH connectivity..."
    if ! ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no root@"$host" "echo 'OK'" > /dev/null 2>&1; then
        log_error "Cannot connect to $host via SSH"
        return 1
    fi
    log_success "SSH connection OK"

    # Check NFS mount
    log "Checking NFS mount /mnt/music..."
    if ! ssh root@"$host" "test -d /mnt/music/home/joe && echo 'OK'" | grep -q "OK"; then
        log_error "NFS mount /mnt/music not accessible on $host"
        return 1
    fi
    log_success "NFS mount accessible"

    # Check Python version
    log "Checking Python version..."
    python_version=$(ssh root@"$host" "python3 --version 2>&1")
    log "  $python_version"

    if ! echo "$python_version" | grep -q "Python 3"; then
        log_error "Python 3 not found on $host"
        return 1
    fi
    log_success "Python 3 found"

    # Check pip
    log "Checking pip..."
    if ! ssh root@"$host" "python3 -m pip --version" > /dev/null 2>&1; then
        log_warn "pip not found, installing..."
        ssh root@"$host" "apt-get update && apt-get install -y python3-pip" || {
            log_error "Failed to install pip"
            return 1
        }
    fi
    log_success "pip available"

    # Clone GitHub repository if not present (MUST happen first)
    log "Checking for GitHub repository..."
    if ! ssh root@"$host" "test -d /root/ImageRecognition/.git && echo 'OK'" | grep -q "OK"; then
        log_warn "Repository not found, cloning from GitHub..."
        ssh root@"$host" "cd /root && git clone https://github.com/Joe-Costa/ImageRecognition.git" || {
            log_error "Failed to clone repository"
            return 1
        }
        log_success "Repository cloned"
    else
        log_success "Repository already exists"
        # Pull latest changes
        log "Pulling latest changes..."
        ssh root@"$host" "cd /root/ImageRecognition && git pull" || {
            log_warn "Failed to pull latest changes (continuing anyway)"
        }
    fi

    # Create virtual environment (force recreate to ensure it's clean)
    log "Setting up Python virtual environment..."
    log "  Removing old venv if exists..."
    ssh root@"$host" "rm -rf /root/ImageRecognition/venv"

    log "  Creating fresh venv..."
    ssh root@"$host" "cd /root/ImageRecognition && python3 -m venv venv" || {
        log_error "Failed to create virtual environment"
        return 1
    }
    log_success "  Virtual environment created"

    # Install Python packages in virtual environment
    log "Installing Python packages in venv..."
    for package in "${PACKAGES[@]}"; do
        log "  Installing $package..."
        if ssh root@"$host" "/root/ImageRecognition/venv/bin/pip install -q $package"; then
            log_success "    $package installed"
        else
            log_error "    Failed to install $package"
            return 1
        fi
    done

    # Verify installations
    log "Verifying package installations..."
    ssh root@"$host" "/root/ImageRecognition/venv/bin/python -c '
import sys
try:
    import sentence_transformers
    import faiss
    import polars
    import PIL
    import numpy
    print(\"All packages imported successfully\")
except ImportError as e:
    print(f\"Import error: {e}\")
    sys.exit(1)
'" || {
        log_error "Package verification failed"
        return 1
    }
    log_success "All packages verified"

    # Create results directory
    log "Creating results directory..."
    ssh root@"$host" "mkdir -p /mnt/music/home/joe/imageindex /mnt/music/home/joe/image_results" || {
        log_error "Failed to create directories"
        return 1
    }
    log_success "Directories created"

    # Check available RAM
    log "Checking available RAM..."
    ram_info=$(ssh root@"$host" "free -h | grep Mem:")
    log "  $ram_info"

    # Check available disk space
    log "Checking disk space on /mnt/music..."
    disk_info=$(ssh root@"$host" "df -h /mnt/music | tail -1")
    log "  $disk_info"

    log_success "Worker $host setup complete!"
    echo
}

# Main setup loop
log "=========================================="
log "Starting worker setup"
log "=========================================="
echo

success_count=0
failed_hosts=()

for host in "${HOSTS[@]}"; do
    if setup_worker "$host"; then
        ((success_count++))
    else
        failed_hosts+=("$host")
        log_error "Setup failed for $host"
    fi
done

# Summary
echo
log "=========================================="
log "Setup Summary"
log "=========================================="
log "Total hosts: ${#HOSTS[@]}"
log_success "Successful: $success_count"

if [ ${#failed_hosts[@]} -gt 0 ]; then
    log_error "Failed: ${#failed_hosts[@]}"
    for host in "${failed_hosts[@]}"; do
        log_error "  - $host"
    done
    exit 1
else
    log_success "All workers set up successfully!"
    echo
    log "You can now run the controller:"
    log "  python3 controller.py \\"
    log "    --image-dir /Volumes/home/joe/images \\"
    log "    --index-prefix /Volumes/home/joe/imageindex"
fi
