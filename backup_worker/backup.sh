#!/bin/sh
set -eu

# Generate a UTC timestamp for the backup filename.
TIMESTAMP=$(date -u +"%y%m%d_%H%M%S")
BACKUP_FILE="/backups/otintel_${TIMESTAMP}.dump"
TEMP_FILE="${BACKUP_FILE}.partial"

# delete incomplete backups if the script exits early
trap 'rm -f "$TEMP_FILE"' EXIT

echo "Starting PostgreSQL backup..."

# Create a custom_format PostgreSQL backup
pg_dump -Fc -f "$TEMP_FILE"

# Verify that PostgreSQL can read the archive.
pg_restore --list "$TEMP_FILE" > /dev/null

# Rename the verified archive to its final filename
mv "$TEMP_FILE" "$BACKUP_FILE"

echo "Backup completed and archive verified."
echo "File: $BACKUP_FILE"