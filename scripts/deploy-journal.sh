#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/lib/deployment.sh"
portal_lock
portal_config
fail(){ portal_fail "$@"; }
ok(){ portal_ok "$@"; }
SKIP_USER=false
[[ ${1:-} == '--skip-user' ]] && SKIP_USER=true
./scripts/check-production-config.sh
set -a; source .env; set +a

portal_postgres false

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

portal_build journal
docker compose run --rm --no-deps -T journal uv run --frozen --no-dev alembic upgrade head
ok 'Journal Alembic migration completed'

if ! $SKIP_USER; then
  printf '\nCreate or update the Journal login user. Password input is hidden.\n'
  docker compose run --rm --no-deps -e JOURNAL_ADMIN_USERNAME=yoiwerr journal uv run --frozen --no-dev python create_user.py
fi

docker compose up -d --no-deps --no-build --wait --wait-timeout 180 journal
portal_proxy
ok 'Journal is available at https://yoiwerr.site/journal/'
