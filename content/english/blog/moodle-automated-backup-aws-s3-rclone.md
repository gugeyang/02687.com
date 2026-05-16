---
title: "Automated Moodle Backup to AWS S3 with Rclone and Cron: A Production Guide"
date: 2026-05-16T12:00:00+08:00
image: "images/blog/blog-post-3.jpg"
author: "Alex Chen"
type: "post"
categories: ["Infrastructure and Cloud", "Dev Log"]
tags: ["Moodle", "AWS S3", "Rclone", "Backup", "Disaster Recovery", "Cron"]
description: "A production guide to automating Moodle backups to AWS S3 using rclone and cron. Covers full backup scope (database + moodledata + config), compression, retention policy, restore testing, and the gotchas that cause silent backup failures in Docker deployments."
---

Moodle's built-in backup tool creates per-course `.mbz` archives. It does not back up your database. It does not back up your `moodledata` directory. It certainly does not put anything in offsite storage automatically. If your server dies and you've been relying on Moodle's built-in course backup feature, you're recovering from memory, not from a backup.

This guide covers what a real Moodle backup looks like: a scripted process that captures the MariaDB database dump, the `moodledata` file directory, and the `config.php`, compresses them, ships them to AWS S3 with rclone, and enforces a retention policy — all running unattended via cron.

## What a Complete Moodle Backup Actually Includes

Before writing any scripts, it's worth being explicit about what needs to be captured. I've seen institutions run database backups for years, then discover during a restore that the `moodledata` directory — which holds all uploaded files, submitted assignments, and course resources — was never included. The database tells Moodle that a file exists; the `moodledata` directory is where the file actually lives.

A complete Moodle backup requires four components:

| Component | What It Contains | Backup Method |
|-----------|-----------------|---------------|
| MariaDB / PostgreSQL database | All course structure, user accounts, grades, activity logs | `mysqldump` or `pg_dump` |
| `moodledata` directory | Uploaded files, submitted assignments, course resources, temp files | `tar` archive |
| `config.php` | Database credentials, `wwwroot`, encryption keys | File copy |
| Moodle application code | The PHP codebase (reproducible from Git/release, lower priority) | Optional |

For disaster recovery, restoring the database and `moodledata` to a fresh Moodle install of the same version is sufficient to recover all data. The application code can be re-downloaded from Moodle's release archive.

## Setting Up Rclone for AWS S3

Rclone is the correct tool for shipping backup archives to S3. It handles multipart uploads for large files, supports server-side encryption, and can enforce lifecycle-aware deletion without requiring the AWS CLI to be configured separately.

Install rclone on Ubuntu:

```bash
curl https://rclone.org/install.sh | sudo bash
```

Configure the S3 remote. Run `rclone config` interactively the first time, or write the config directly:

```ini
# ~/.config/rclone/rclone.conf

[moodle-s3]
type = s3
provider = AWS
env_auth = false
access_key_id = AKIAIOSFODNN7EXAMPLE
secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
region = ap-southeast-1
location_constraint = ap-southeast-1
acl = private
server_side_encryption = AES256
storage_class = STANDARD_IA
```

Using `STANDARD_IA` (Infrequent Access) storage class for backups cuts S3 costs by approximately 40% compared to standard storage, with no meaningful difference in restore access times for disaster recovery scenarios where you retrieve a backup once every few months at most.

Test the connection:

```bash
rclone lsd moodle-s3:your-backup-bucket-name
```

## The Backup Script: Database + Moodledata in One Shot

Save this script as `/usr/local/bin/moodle-backup.sh` and make it executable:

```bash
#!/bin/bash
# /usr/local/bin/moodle-backup.sh
# Full Moodle backup: MariaDB dump + moodledata + config.php → S3

set -euo pipefail

# --- Configuration ---
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/tmp/moodle-backup-${TIMESTAMP}"
ARCHIVE_NAME="moodle-full-backup-${TIMESTAMP}.tar.gz"
S3_REMOTE="moodle-s3:your-backup-bucket-name/backups"
RETENTION_DAYS=30

# Moodle-specific paths (adjust for your deployment)
MOODLE_DATA="/var/moodledata"
MOODLE_CONFIG="/var/www/html/moodle/config.php"
DB_NAME="moodle"
DB_USER="moodleuser"
DB_PASS="your-db-password"
DB_HOST="mariadb"  # Docker service name or localhost

# --- Create temp directory ---
mkdir -p "${BACKUP_DIR}"
echo "[$(date)] Starting Moodle backup: ${TIMESTAMP}"

# --- Step 1: Database dump ---
echo "[$(date)] Dumping MariaDB database..."
mysqldump \
    --host="${DB_HOST}" \
    --user="${DB_USER}" \
    --password="${DB_PASS}" \
    --single-transaction \
    --routines \
    --triggers \
    "${DB_NAME}" | gzip > "${BACKUP_DIR}/moodle-db-${TIMESTAMP}.sql.gz"

echo "[$(date)] Database dump complete: $(du -sh ${BACKUP_DIR}/moodle-db-${TIMESTAMP}.sql.gz | cut -f1)"

# --- Step 2: Moodledata directory ---
echo "[$(date)] Archiving moodledata directory..."
tar -czf "${BACKUP_DIR}/moodledata-${TIMESTAMP}.tar.gz" \
    --exclude="${MOODLE_DATA}/cache" \
    --exclude="${MOODLE_DATA}/localcache" \
    --exclude="${MOODLE_DATA}/temp" \
    --exclude="${MOODLE_DATA}/trashdir" \
    "${MOODLE_DATA}"

echo "[$(date)] Moodledata archive: $(du -sh ${BACKUP_DIR}/moodledata-${TIMESTAMP}.tar.gz | cut -f1)"

# --- Step 3: config.php ---
cp "${MOODLE_CONFIG}" "${BACKUP_DIR}/config-${TIMESTAMP}.php"

# --- Step 4: Bundle everything into one archive ---
tar -czf "/tmp/${ARCHIVE_NAME}" -C /tmp "moodle-backup-${TIMESTAMP}"
rm -rf "${BACKUP_DIR}"

echo "[$(date)] Final archive: $(du -sh /tmp/${ARCHIVE_NAME} | cut -f1)"

# --- Step 5: Upload to S3 ---
echo "[$(date)] Uploading to S3..."
rclone copy "/tmp/${ARCHIVE_NAME}" "${S3_REMOTE}/" \
    --s3-chunk-size=64M \
    --progress

# --- Step 6: Cleanup local temp file ---
rm -f "/tmp/${ARCHIVE_NAME}"

# --- Step 7: Enforce S3 retention policy ---
echo "[$(date)] Pruning backups older than ${RETENTION_DAYS} days..."
rclone delete "${S3_REMOTE}/" \
    --min-age "${RETENTION_DAYS}d"

echo "[$(date)] Backup complete."
```

Make it executable and test it manually before scheduling:

```bash
chmod +x /usr/local/bin/moodle-backup.sh
sudo /usr/local/bin/moodle-backup.sh 2>&1 | tee /var/log/moodle-backup.log
```

## Scheduling Automated Backups with Cron

Add the backup to root's crontab for nightly execution:

```bash
# crontab -e (as root)

# Moodle full backup — runs at 02:30 AM daily
30 2 * * * /usr/local/bin/moodle-backup.sh >> /var/log/moodle-backup.log 2>&1
```

Running at 02:30 AM avoids overlap with Moodle's own maintenance cron window (which typically runs at 00:00 and 01:00) and minimizes the chance of a backup running during peak user activity. If your institution spans multiple time zones, adjust to the lowest-traffic window for your primary student population.

For Docker deployments where the database runs in a container, the `mysqldump` command needs to run inside the database container. Replace the mysqldump step with:

```bash
docker exec moodle_mariadb mysqldump \
    --user="${DB_USER}" \
    --password="${DB_PASS}" \
    --single-transaction \
    "${DB_NAME}" | gzip > "${BACKUP_DIR}/moodle-db-${TIMESTAMP}.sql.gz"
```

## Gotchas That Cause Silent Moodle Backup Failures

**1. The backup script completes without error but the database dump is empty.**

This happens when `mysqldump` encounters an authentication error but the shell script continues because the exit code handling was not strict. The gzipped output file is created (it contains the gzip header) but is effectively empty — 20 bytes instead of several hundred MB.

Fix: use `set -euo pipefail` at the top of every backup script (included in the script above). This causes the script to exit immediately if any command fails, including `mysqldump`. Monitor the backup log for "Backup complete" as confirmation, not just script exit code 0.

**2. The `moodledata` backup is 10x larger than expected because cache directories were included.**

Moodle stores transient cache data, temp files, and session data inside `moodledata` subdirectories. These directories can be gigabytes in size and are completely unnecessary to back up — Moodle regenerates them automatically. The `--exclude` flags in the script above remove `cache`, `localcache`, `temp`, and `trashdir`. Always verify your backup size is reasonable; a backup that grows unexpectedly fast is probably including cache.

**3. Rclone upload fails halfway through for backups larger than 5GB.**

AWS S3 requires multipart upload for files over 5GB. Rclone handles this automatically with `--s3-chunk-size`, but the default chunk size of 5MB creates thousands of small parts for large backups, which can hit S3 API rate limits. The `--s3-chunk-size=64M` flag in the script above is a safe value for most deployment sizes up to ~50GB archives.

## Restore Testing: The Step Everyone Skips Until Disaster

A backup you've never tested is not a backup — it's a hope. Schedule a quarterly restore test:

```bash
# Download the latest backup from S3
rclone copy moodle-s3:your-backup-bucket-name/backups/ /tmp/restore-test/ \
    --include "moodle-full-backup-*.tar.gz" \
    --max-age 24h

# Extract on a test server or a separate Docker environment
tar -xzf /tmp/restore-test/moodle-full-backup-*.tar.gz -C /tmp/

# Restore database to a test MariaDB instance
zcat moodle-db-*.sql.gz | mysql --host=test-db --user=moodleuser --password moodle_restore

# Restore moodledata
tar -xzf moodledata-*.tar.gz -C /var/moodledata-restored/
```

Verify that Moodle starts correctly with the restored data by pointing a staging `config.php` at the restored database and moodledata path. Check that a known course, its files, and recent submissions are present.

The restore test also validates that your S3 access credentials still work and that the archive format hasn't drifted. I've seen a backup script that produced valid archives for months, then silently started producing corrupted `.tar.gz` files after a system update changed the `tar` binary version. The corruption was only caught during a quarterly restore test — not during an actual disaster.

For a production Moodle deployment that takes backup integrity seriously, the monitoring layer should include alerts for backup job failures. Our [Prometheus and Grafana LMS Monitoring](/blog/prometheus-grafana-lms-monitoring/) guide covers how to expose custom metrics from shell scripts. For the full self-hosted Moodle stack context — including the Docker Compose setup that this backup script targets — see [Self-Hosting Educational Tools with Docker and HomeLab](/blog/self-hosting-educational-tools-docker-homelab/).
