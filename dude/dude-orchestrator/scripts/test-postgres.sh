#!/usr/bin/env bash
# A fresh disposable cluster; never inherit a business database URL.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(id -u)" == 0 ]]; then
  echo 'Run as a non-root development user; initdb refuses root.' >&2
  exit 1
fi
pg_bin="${DUDE_TEST_PG_BIN:-$(pg_config --bindir)}"
port="${DUDE_TEST_PG_PORT:-15438}"
if ! [[ "$port" =~ ^[0-9]+$ ]] || (( port < 1024 || port > 65535 )); then
  echo 'Choose an unprivileged test port between 1024 and 65535.' >&2
  exit 1
fi
work="$(mktemp -d /tmp/dude-orchestrator-test.XXXXXXXX)"
started=false
cleanup() {
  if [[ "$started" == true ]]; then
    if ! "$pg_bin/pg_ctl" -D "$work/data" -m fast -w stop >/dev/null; then
      echo "Could not stop test cluster; retained $work for inspection." >&2
      return 1
    fi
  fi
  # Only remove our freshly allocated direct child of /tmp.
  if [[ "$work" =~ ^/tmp/dude-orchestrator-test\.[a-zA-Z0-9]+$ && ! -L "$work" ]]; then
    rm -rf -- "$work"
  fi
}
trap cleanup EXIT
export PGPASSWORD="$(node -e "process.stdout.write(require('node:crypto').randomBytes(24).toString('hex'))")"
umask 077
printf '%s' "$PGPASSWORD" > "$work/password"
"$pg_bin/initdb" -D "$work/data" --username=dude_test_runner --auth=scram-sha-256 \
  --encoding=UTF8 --locale=C --pwfile="$work/password" > "$work/init.log"
if ! "$pg_bin/pg_ctl" -D "$work/data" -l "$work/postgres.log" \
  -o "-h 127.0.0.1 -p $port -k $work" -w start >/dev/null; then
  cat "$work/postgres.log" >&2
  exit 1
fi
started=true
database="dude_orchestrator_test_$(node -e "process.stdout.write(require('node:crypto').randomBytes(8).toString('hex'))")"
"$pg_bin/createdb" -h 127.0.0.1 -p "$port" -U dude_test_runner "$database"
export DUDE_TEST_DATABASE_URL="postgresql://dude_test_runner:$PGPASSWORD@127.0.0.1:$port/$database"
unset DUDE_ORCHESTRATOR_DATABASE_URL DATABASE_URL JWT_SECRET
npm test
