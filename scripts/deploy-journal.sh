#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
fail(){ printf '[ERROR] %s\n' "$*" >&2; exit 1; }
ok(){ printf '[OK] %s\n' "$*"; }
SKIP_USER=false
[[ ${1:-} == '--skip-user' ]] && SKIP_USER=true
./scripts/check-production-config.sh
set -a; source .env; set +a

docker compose up -d postgres
for _ in $(seq 1 30); do
  [[ "$(docker inspect --format='{{.State.Health.Status}}' chalab-postgres 2>/dev/null || true)" == healthy ]] && break
  sleep 2
done
[[ "$(docker inspect --format='{{.State.Health.Status}}' chalab-postgres 2>/dev/null || true)" == healthy ]] || fail 'existing PostgreSQL container is not healthy'

# This runs against the existing volume; it creates only the missing Journal role/database.
docker compose exec -T -e JOURNAL_DB_PASSWORD="$JOURNAL_DB_PASSWORD" postgres sh -ceu '
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -v journal_password="$JOURNAL_DB_PASSWORD" <<"SQL"
SELECT format('"'"'CREATE ROLE journal_user LOGIN PASSWORD %L'"'"', :'"'"'journal_password'"'"')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '"'"'journal_user'"'"') \gexec
SELECT format('"'"'ALTER ROLE journal_user PASSWORD %L'"'"', :'"'"'journal_password'"'"') \gexec
SELECT '"'"'CREATE DATABASE journal OWNER journal_user'"'"'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '"'"'journal'"'"') \gexec
SQL
'
ok 'journal_user and journal database are ready'

docker compose build journal
docker compose run --rm journal uv run alembic upgrade head
ok 'Journal Alembic migration completed'

if ! $SKIP_USER; then
  printf '\nCreate or update the Journal login user. Password input is hidden.\n'
  docker compose run --rm -e JOURNAL_ADMIN_USERNAME=yoiwerr journal uv run python create_user.py
fi

docker compose up -d --no-deps journal
for _ in $(seq 1 30); do
  [[ "$(docker inspect --format='{{.State.Health.Status}}' portal-journal 2>/dev/null || true)" == healthy ]] && break
  sleep 2
done
[[ "$(docker inspect --format='{{.State.Health.Status}}' portal-journal 2>/dev/null || true)" == healthy ]] || { docker compose logs --tail=100 journal; fail 'Journal did not become healthy'; }

docker compose run --rm --no-deps nginx nginx -t
docker compose up -d --no-deps --force-recreate nginx
curl --fail --silent --show-error --insecure --resolve yoiwerr.site:443:127.0.0.1 https://yoiwerr.site/journal/health >/dev/null
ok 'Journal is available at https://yoiwerr.site/journal/'
