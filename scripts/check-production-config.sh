#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
fail(){ printf '[ERROR] %s\n' "$*" >&2; exit 1; }
command -v docker >/dev/null || fail 'Docker is not installed'
docker compose version >/dev/null 2>&1 || fail 'Docker Compose v2 plugin is required'
version="$(docker compose version --short | sed 's/^v//')"
printf '%s\n%s\n' '2.20.0' "$version" | sort -V -C || fail "Docker Compose >= 2.20.0 required (found $version)"
[[ -f .env ]] || fail '.env is missing; copy .env.example and fill production values'
set -a
# .env is an administrator-owned deployment file and must contain shell-compatible KEY=VALUE lines.
source .env
set +a
for name in PGSQLPASSWORD JOURNAL_DB_PASSWORD JWT_SECRET ADMIN_INIT_PASSWORD; do
  [[ -n "${!name:-}" ]] || fail "$name is missing in .env"
done
[[ ${#JOURNAL_DB_PASSWORD} -ge 20 ]] || fail 'JOURNAL_DB_PASSWORD must be at least 20 characters'
[[ ${#JWT_SECRET} -ge 32 ]] || fail 'JWT_SECRET must be at least 32 characters'
[[ -f /etc/letsencrypt/live/yoiwerr.site/fullchain.pem ]] || fail 'TLS certificate fullchain.pem is missing'
[[ -f /etc/letsencrypt/live/yoiwerr.site/privkey.pem ]] || fail 'TLS private key is missing'
docker compose config --quiet
printf '[OK] production configuration is valid\n'
