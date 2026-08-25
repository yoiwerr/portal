#!/usr/bin/env bash
set -Eeuo pipefail
db="${1:?usage: restore.sh database dump}"; dump="${2:?usage: restore.sh database dump}"
portal_dir="${PORTAL_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"; cd "$portal_dir"
[[ -f "$dump" ]] || { echo 'dump not found' >&2; exit 1; }
[[ "$db" =~ ^(journal|makeitspecific|alfred|chatdemopg)$ ]] || { echo 'refusing unknown target' >&2; exit 1; }
docker compose exec -T postgres pg_restore --list <"$dump" >/dev/null
printf 'Target database: %s\nBackup file: %s\n' "$db" "$(readlink -f "$dump")"
read -r -p "Type RESTORE $db to confirm: " confirm
[[ "$confirm" == "RESTORE $db" ]] || { echo 'cancelled'; exit 1; }
docker compose exec -T postgres sh -ceu 'exec pg_restore -U "$POSTGRES_USER" --clean --if-exists --no-owner --no-privileges --dbname="$1"' sh "$db" <"$dump"
