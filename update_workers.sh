#!/bin/bash
#
# Quick script to update code on all workers from GitHub
#
# Usage:
#   ./update_workers.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOSTS_FILE="${SCRIPT_DIR}/hosts"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[UPDATE]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[UPDATE]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[UPDATE]${NC} $1"
}

log_error() {
    echo -e "${RED}[UPDATE]${NC} $1"
}

# Check if hosts file exists
if [ ! -f "$HOSTS_FILE" ]; then
    log_error "Hosts file not found: $HOSTS_FILE"
    exit 1
fi

# Read hosts (compatible with macOS bash)
HOSTS=()
while IFS= read -r line; do
    [[ -n "$line" && ! "$line" =~ ^# ]] && HOSTS+=("$line")
done < "$HOSTS_FILE"

if [ ${#HOSTS[@]} -eq 0 ]; then
    log_error "No hosts found in $HOSTS_FILE"
    exit 1
fi

log "Updating ${#HOSTS[@]} workers from GitHub..."
echo

success_count=0
failed_hosts=()

for host in "${HOSTS[@]}"; do
    log "Updating $host..."

    # Check if repository exists
    if ! ssh -o ConnectTimeout=5 root@"$host" "test -d /root/ImageRecognition/.git" 2>/dev/null; then
        log_warn "$host: Repository not found, cloning..."
        if ssh root@"$host" "cd /root && git clone https://github.com/Joe-Costa/ImageRecognition.git" 2>/dev/null; then
            log_success "$host: Repository cloned"
            ((success_count++))
        else
            log_error "$host: Failed to clone repository"
            failed_hosts+=("$host")
        fi
        continue
    fi

    # Pull latest changes
    pull_output=$(ssh root@"$host" "cd /root/ImageRecognition && git pull" 2>&1)
    pull_result=$?

    if [ $pull_result -eq 0 ]; then
        # Get current commit
        commit=$(ssh root@"$host" "cd /root/ImageRecognition && git log -1 --oneline" 2>/dev/null)
        log_success "$host: Updated - $commit"
        ((success_count++))
    else
        log_error "$host: Failed to pull changes"
        log_error "  Error output: $pull_output"
        failed_hosts+=("$host")
    fi
done

# Summary
echo
log "========================================"
log "Update Summary"
log "========================================"
log "Total hosts: ${#HOSTS[@]}"
log_success "Successful: $success_count"

if [ ${#failed_hosts[@]} -gt 0 ]; then
    log_error "Failed: ${#failed_hosts[@]}"
    for host in "${failed_hosts[@]}"; do
        log_error "  - $host"
    done
    exit 1
else
    log_success "All workers updated successfully!"
fi
