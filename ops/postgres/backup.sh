#!/usr/bin/env bash
set -Eeuo pipefail
db="${1:?usage: backup.sh database}"
[[ "$db" =~ ^[a-zA-Z0-9_]+$ ]] || { echo 'invalid database name' >&2; exit 1; }
portal_dir="${PORTAL_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"; out_dir="${BACKUP_DIR:-/var/backups/portal/postgres}"
cd "$portal_dir"; mkdir -p "$out_dir"
file="$out_dir/${db}-$(date -u +%Y%m%dT%H%M%SZ).dump"; tmp="${file}.partial"
trap 'rm -f "$tmp"' EXIT
docker compose exec -T postgres sh -ceu 'exec pg_dump -U "$POSTGRES_USER" --format=custom --no-owner --no-privileges "$1"' sh "$db" >"$tmp"
docker compose exec -T postgres pg_restore --list <"$tmp" >/dev/null
mv "$tmp" "$file"; trap - EXIT
find "$out_dir" -name "$db-*.dump" -type f -mtime +7 -delete
printf '%s\n' "$file"
