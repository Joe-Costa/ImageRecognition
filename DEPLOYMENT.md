# Deployment Guide - GitHub-Based Workflow

## Overview

This system uses GitHub for code deployment to workers. The repository at https://github.com/Joe-Costa/ImageRecognition is cloned to `/root/ImageRecognition` on each worker host.

## Deployment Workflow

```
Local Mac Development                  GitHub Repository                  Worker Hosts
-------------------                  ------------------                  ------------
Edit code locally
    |
    | git add/commit/push
    v
https://github.com/Joe-Costa/ImageRecognition
                                           |
                                           | git clone (first time)
                                           | git pull (updates)
                                           v
                                     /root/ImageRecognition/
                                     (on duc212, duc213, duc214, duc17)
```

## Initial Setup on Workers

### Option 1: Automated (Recommended)

The `setup_workers.sh` script handles everything automatically:

```bash
# From your Mac
cd /Users/joe/Python_Projects/ImageRecognition
./setup_workers.sh
```

This will:
1. Check if `/root/ImageRecognition` exists on each worker
2. Clone from GitHub if missing
3. Pull latest changes if already cloned
4. Install Python dependencies
5. Create necessary directories

### Option 2: Manual

Clone repository on each worker manually:

```bash
# SSH to each worker and run:
ssh root@duc212-100g.eng.qumulo.com
cd /root
git clone https://github.com/Joe-Costa/ImageRecognition.git
exit

ssh root@duc213-100g.eng.qumulo.com
cd /root
git clone https://github.com/Joe-Costa/ImageRecognition.git
exit

ssh root@duc214-100g.eng.qumulo.com
cd /root
git clone https://github.com/Joe-Costa/ImageRecognition.git
exit

ssh root@duc17-40g.eng.qumulo.com
cd /root
git clone https://github.com/Joe-Costa/ImageRecognition.git
exit
```

Then run setup script to install dependencies:
```bash
./setup_workers.sh
```

## Updating Code on Workers

### After Making Changes

1. **Edit code locally** on your Mac
2. **Commit and push** to GitHub:
   ```bash
   cd /Users/joe/Python_Projects/ImageRecognition
   git add .
   git commit -m "Description of changes"
   git push
   ```

3. **Update workers** (choose one method):

   **Method A: Automated update all workers**
   ```bash
   ./setup_workers.sh
   ```
   (This runs `git pull` automatically)

   **Method B: Manual update specific worker**
   ```bash
   ssh root@duc17-40g.eng.qumulo.com "cd /root/ImageRecognition && git pull"
   ```

   **Method C: Update all workers with loop**
   ```bash
   for host in $(cat hosts); do
       echo "Updating $host..."
       ssh root@$host "cd /root/ImageRecognition && git pull"
   done
   ```

## Directory Structure on Workers

After deployment, workers will have:

```
/root/ImageRecognition/          # Git repository root
├── controller.py                # (not used on workers)
├── worker_index.py              # Used for indexing
├── remote_query.py              # Used for queries
├── merge_indexes.py             # (not used on workers)
├── query_client.py              # (not used on workers)
├── requirements.txt             # Python dependencies
├── hosts                        # Worker list
└── *.md                         # Documentation
```

## File Locations Reference

| Purpose | Path on Worker | Path on Mac |
|---------|----------------|-------------|
| Code repository | `/root/ImageRecognition/` | `/Users/joe/Python_Projects/ImageRecognition/` |
| Image source | `/mnt/music/home/joe/images` | `/Volumes/home/joe/images` |
| Index output | `/mnt/music/home/joe/imageindex` | `/Volumes/home/joe/imageindex` |
| Query results | `/mnt/music/home/joe/image_results` | `/Volumes/home/joe/image_results` |

## Common Tasks

### Check Current Version on Worker

```bash
ssh root@duc17-40g.eng.qumulo.com "cd /root/ImageRecognition && git log -1 --oneline"
```

### Check if Workers are Up-to-Date

```bash
for host in $(cat hosts); do
    echo "=== $host ==="
    ssh root@$host "cd /root/ImageRecognition && git status"
done
```

### Force Update (Discard Local Changes on Worker)

```bash
ssh root@duc17-40g.eng.qumulo.com "cd /root/ImageRecognition && git reset --hard origin/master && git pull"
```

### View Uncommitted Changes on Worker

```bash
ssh root@duc17-40g.eng.qumulo.com "cd /root/ImageRecognition && git diff"
```

## Troubleshooting

### Repository Not Found on Worker

```bash
# Clone it:
ssh root@duc17-40g.eng.qumulo.com "cd /root && git clone https://github.com/Joe-Costa/ImageRecognition.git"
```

### Git Pull Fails (Merge Conflicts)

This shouldn't happen since workers don't edit files, but if it does:

```bash
# Discard worker changes and pull fresh:
ssh root@duc17-40g.eng.qumulo.com "cd /root/ImageRecognition && git reset --hard HEAD && git pull"
```

### Permission Denied

Check SSH keys:
```bash
ssh root@duc17-40g.eng.qumulo.com "echo OK"
```

### Git Not Installed

```bash
ssh root@duc17-40g.eng.qumulo.com "apt-get update && apt-get install -y git"
```

## Development Workflow

### Typical Development Cycle

1. **Develop locally** on Mac:
   ```bash
   cd /Users/joe/Python_Projects/ImageRecognition
   # Edit files in your favorite editor
   ```

2. **Test locally** (if possible):
   ```bash
   python3 controller.py --help
   python3 query_client.py --help
   ```

3. **Commit changes**:
   ```bash
   git add controller.py worker_index.py remote_query.py
   git commit -m "Fixed batch size calculation"
   git push
   ```

4. **Deploy to workers**:
   ```bash
   ./setup_workers.sh
   # or
   for host in $(cat hosts); do ssh root@$host "cd /root/ImageRecognition && git pull"; done
   ```

5. **Test on worker**:
   ```bash
   python3 query_client.py --text "test query" --top-k 3
   ```

### Hot Fix Workflow (Urgent Changes)

If you need to make a quick fix:

```bash
# 1. Edit file locally
vim worker_index.py

# 2. Commit and push
git add worker_index.py
git commit -m "Hotfix: Fixed memory leak in batch processing"
git push

# 3. Update specific worker immediately
ssh root@duc17-40g.eng.qumulo.com "cd /root/ImageRecognition && git pull"

# 4. Test
python3 query_client.py --text "test" --worker duc17-40g.eng.qumulo.com
```

## GitHub Repository Management

### Viewing Repository Status

```bash
# Check what's committed locally but not pushed
git status

# View recent commits
git log --oneline -10

# See what changed in last commit
git show
```

### Creating Branches (Optional)

For major changes, use branches:

```bash
# Create and switch to development branch
git checkout -b dev-new-feature

# Make changes, commit
git add .
git commit -m "Experimental feature"
git push -u origin dev-new-feature

# On workers, switch to this branch for testing
ssh root@duc17-40g.eng.qumulo.com "cd /root/ImageRecognition && git fetch && git checkout dev-new-feature"

# After testing, merge to master
git checkout master
git merge dev-new-feature
git push

# Update workers back to master
for host in $(cat hosts); do
    ssh root@$host "cd /root/ImageRecognition && git checkout master && git pull"
done
```

## Best Practices

1. **Always commit before deploying**
   - Don't leave uncommitted changes on your Mac
   - Workers pull from GitHub, not from your local machine

2. **Test locally first** (when possible)
   - Validate syntax: `python3 -m py_compile script.py`
   - Test imports work

3. **Use meaningful commit messages**
   - Bad: "fixes"
   - Good: "Fixed batch size calculation for 15GB RAM workers"

4. **Update all workers together**
   - Keep workers on same version
   - Use `setup_workers.sh` to update all at once

5. **Document changes**
   - Update README files when adding features
   - Keep CHANGES.md up to date

## Automation Scripts

### Quick Update Script

Save as `update_workers.sh`:

```bash
#!/bin/bash
# Quick script to update all workers

echo "Updating workers from GitHub..."
for host in $(cat hosts); do
    echo "=== Updating $host ==="
    ssh root@$host "cd /root/ImageRecognition && git pull"
done
echo "All workers updated!"
```

Make executable:
```bash
chmod +x update_workers.sh
./update_workers.sh
```

### Check Versions Script

Save as `check_versions.sh`:

```bash
#!/bin/bash
# Check git version on all workers

echo "Checking worker versions..."
for host in $(cat hosts); do
    echo "=== $host ==="
    ssh root@$host "cd /root/ImageRecognition && git log -1 --oneline"
done
```

## See Also

- `README_DISTRIBUTED.md` - Full system documentation
- `QUICKSTART.md` - Quick reference
- `setup_workers.sh` - Automated deployment script
