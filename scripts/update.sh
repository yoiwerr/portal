#!/usr/bin/env bash
# Pull source separately with git pull --ff-only; this script never merges code.
set -Eeuo pipefail
source "$(dirname "$0")/lib/deployment.sh"
scope=dude
initial=false
build=true
for arg in "$@"; do
  case "$arg" in
    dude|journal|all|nginx) scope=$arg ;;
    --rebuild|-f) scope=all ;;
    --initial) initial=true; scope=all ;;
    --no-build) build=false ;;
    *) portal_fail 'Usage: scripts/update.sh [dude|journal|all|nginx] [--no-build] (default: dude)' ;;
  esac
done
portal_lock
portal_config
./scripts/check-production-config.sh
services=()
case "$scope" in
  dude) services=(dude-admin dude-api) ;;
  journal) services=(journal) ;;
  all) services=(dude-admin dude-api journal) ;;
esac
portal_postgres "$initial"
if ((${#services[@]})); then
  if $build; then portal_build "${services[@]}"; fi
  if $initial; then ./ops/postgres/init-projects.sh; fi
  portal_start "${services[@]}"
fi
portal_proxy
docker compose ps
portal_ok "Update finished: $scope (git $(git rev-parse --short HEAD))"
