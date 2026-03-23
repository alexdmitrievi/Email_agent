#!/bin/bash
# Database backup script for Email Agent
# Usage: ./scripts/backup.sh
# Cron example: 0 3 * * * /app/scripts/backup.sh >> /var/log/backup.log 2>&1

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
PG_DB="${PG_DB:-email_agent}"
PG_USER="${PG_USER:-agent}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# PostgreSQL dump
DUMP_FILE="$BACKUP_DIR/${PG_DB}_${TIMESTAMP}.sql.gz"
pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
    --no-owner --no-privileges --clean --if-exists \
    | gzip > "$DUMP_FILE"

SIZE=$(du -h "$DUMP_FILE" | cut -f1)
echo "[$(date)] Backup created: $DUMP_FILE ($SIZE)"

# Clean old backups
DELETED=$(find "$BACKUP_DIR" -name "*.sql.gz" -mtime +${RETENTION_DAYS} -delete -print | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "[$(date)] Deleted $DELETED old backups (>${RETENTION_DAYS} days)"
fi

# Verify backup is not empty
if [ ! -s "$DUMP_FILE" ]; then
    echo "[$(date)] ERROR: Backup file is empty!"
    exit 1
fi

echo "[$(date)] Backup complete."
