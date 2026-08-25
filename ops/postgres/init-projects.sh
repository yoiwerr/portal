#!/usr/bin/env bash
set -Eeuo pipefail
portal_dir="${PORTAL_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"; cd "$portal_dir"
[[ -f .env ]] || { echo '.env is required' >&2; exit 1; }
set -a; source .env; set +a
: "${JOURNAL_DB_PASSWORD:?set JOURNAL_DB_PASSWORD}"
: "${MAKEITSPECIFIC_DB_PASSWORD:?set MAKEITSPECIFIC_DB_PASSWORD}"
docker compose up -d postgres
docker compose exec -T -e JOURNAL_DB_PASSWORD -e MAKEITSPECIFIC_DB_PASSWORD postgres sh -ceu '
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -v journal_password="$JOURNAL_DB_PASSWORD" -v specific_password="$MAKEITSPECIFIC_DB_PASSWORD" <<"SQL"
SELECT format('"'"'CREATE ROLE journal_user LOGIN PASSWORD %L'"'"', :'"'"'journal_password'"'"') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='"'"'journal_user'"'"') \gexec
SELECT format('"'"'ALTER ROLE journal_user PASSWORD %L'"'"', :'"'"'journal_password'"'"') \gexec
SELECT '"'"'CREATE DATABASE journal OWNER journal_user'"'"' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='"'"'journal'"'"') \gexec
SELECT format('"'"'CREATE ROLE makeitspecific_user LOGIN PASSWORD %L'"'"', :'"'"'specific_password'"'"') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='"'"'makeitspecific_user'"'"') \gexec
SELECT format('"'"'ALTER ROLE makeitspecific_user PASSWORD %L'"'"', :'"'"'specific_password'"'"') \gexec
SELECT '"'"'CREATE DATABASE makeitspecific OWNER makeitspecific_user'"'"' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='"'"'makeitspecific'"'"') \gexec
SQL
'
echo 'project roles and databases are ready; existing alfred database was not changed'
