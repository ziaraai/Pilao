#!/usr/bin/env bash
# Nightly backup of the database and of the files, 14 days kept.
# Plesk > Tools & Settings > Scheduled Tasks (cron), as root, every day at 03:15:
#   /opt/pilao/backup.sh >> /var/log/pilao-backup.log 2>&1
# Restore (docs/14): pg_restore into the postgres container, untar into the files volume.
set -euo pipefail
cd "$(dirname "$0")"
dest=${PILAO_BACKUP_DIR:-/var/backups/pilao}
keep=${PILAO_BACKUP_DAYS:-14}
day=$(date +%F)
install -d -m 700 "$dest"
./pilao.sh exec -T postgres pg_dump -U pilao -d pilao --format=custom > "$dest/base-$day.dump.part"
mv "$dest/base-$day.dump.part" "$dest/base-$day.dump"
docker run --rm -v pilao_files:/data:ro -v "$dest":/backup alpine:3.20 \
  tar czf "/backup/fichiers-$day.tgz" -C /data .
cp secrets.env "$dest/secrets-$day.env"  # without it the dump's password is lost
chmod 600 "$dest"/*
find "$dest" -type f -mtime +"$keep" -delete
echo "$(date -u +%FT%TZ) backup $day: $(du -sh "$dest" | cut -f1) in $dest"
