#!/usr/bin/env bash
# Shared by build/update/deploy entry points. Do not source from application code.
set -Eeuo pipefail
PORTAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PORTAL_ROOT"
portal_fail() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }
portal_ok() { printf '[OK] %s\n' "$*"; }
trap 'printf "[ERROR] Deployment stopped at line %s (exit %s); inspect service/build logs.\n" "$LINENO" "$?" >&2' ERR
portal_cleanup() {
  if [[ ${PORTAL_BUILDER_ACTIVE:-false} == true ]]; then
    docker buildx stop "$PORTAL_BUILDER" >/dev/null 2>&1 || true
  fi
}
trap portal_cleanup EXIT

portal_lock() {
  command -v flock >/dev/null || portal_fail 'Install util-linux (flock) first'
  exec 9> .portal-deploy.lock
  flock -n 9 || portal_fail 'Another Portal build/deployment is running; wait for it to finish'
}

portal_config() {
  command -v docker >/dev/null || portal_fail 'Docker is required'
  command -v python3 >/dev/null || portal_fail 'Python 3 is required'
  command -v curl >/dev/null || portal_fail 'curl is required'
  [[ -f .env ]] || portal_fail 'Copy .env.example to .env only if absent, then fill credentials'
  set -a
  source .env
  set +a
  docker compose config --quiet
}

portal_services() {
  (($#)) || portal_fail 'Specify at least one application service'
  local service
  for service in "$@"; do
    case "$service" in dude-api|dude-admin|journal) ;; *) portal_fail "Unsupported build service: $service" ;; esac
  done
}

portal_builder() {
  # Limits apply to the whole build container, including its RUN/compile children.
  # compose build --memory does NOT cap BuildKit. Do not fall back to it.
  PORTAL_BUILDER=portal-low-memory
  docker buildx version >/dev/null
  local available disk
  available=$(awk '/MemAvailable:/ {print int($2 / 1024)}' /proc/meminfo)
  disk=$(df -Pm "$PORTAL_ROOT" | awk 'NR==2 {print $4}')
  [[ $available -ge 256 ]] || portal_fail "Only ${available} MiB RAM available; stop verified unused services before building"
  [[ $disk -ge 4096 ]] || portal_fail "Only ${disk} MiB disk free; need at least 4 GiB for build/cache"
  if ! docker buildx inspect "$PORTAL_BUILDER" >/dev/null 2>&1; then
    docker buildx create --name "$PORTAL_BUILDER" --driver docker-container \
      --driver-opt image=moby/buildkit:v0.20.2 \
      --driver-opt memory=512m --driver-opt memory-swap=1g \
      --driver-opt cpu-period=100000 --driver-opt cpu-quota=75000 \
      --buildkitd-config "$PORTAL_ROOT/ops/buildkit/buildkitd.toml"
  fi
  PORTAL_BUILDER_ACTIVE=true
  docker buildx inspect --bootstrap "$PORTAL_BUILDER" >/dev/null
  # Verify actual Docker limits, including on an existing builder of the same name.
  local limits
  limits=$(docker inspect --format '{{.HostConfig.Memory}} {{.HostConfig.MemorySwap}} {{.HostConfig.CpuPeriod}} {{.HostConfig.CpuQuota}}' "buildx_buildkit_${PORTAL_BUILDER}0")
  [[ $limits == '536870912 1073741824 100000 75000' ]] || portal_fail "Builder limits differ; stop/remove only $PORTAL_BUILDER and retry (see docs/small-server-deployment.md)"
}

portal_build() {
  portal_services "$@"
  portal_builder
  local service container image stamp
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  for service in "$@"; do
    # Keep the previous running image available; never prune it during deployment.
    container=$(docker compose ps --all --quiet "$service")
    if [[ -n $container ]]; then
      image=$(docker inspect --format '{{.Image}}' "$container")
      docker image tag "$image" "portal-rollback/$service:$stamp"
      printf '[INFO] Previous image: portal-rollback/%s:%s\n' "$service" "$stamp"
    fi
    printf '[INFO] Building %s sequentially (512 MiB, 0.75 CPU)\n' "$service"
    COMPOSE_PARALLEL_LIMIT=1 docker compose --progress plain build --builder "$PORTAL_BUILDER" "$service"
  done
  # Release BuildKit's idle memory; its persistent cache volume remains.
  docker buildx stop "$PORTAL_BUILDER"
  PORTAL_BUILDER_ACTIVE=false
}

portal_postgres() {
  local initial=${1:-false} container
  container=$(docker compose ps --all --quiet postgres)
  if [[ -z $container && $initial != true ]]; then
    portal_fail 'Existing PostgreSQL container not found; check Compose project name. Only a first installation may use deploy.sh'
  fi
  # Start the existing container without applying config changes/recreating it.
  docker compose up -d --no-recreate --wait --wait-timeout 180 postgres
}

portal_start() {
  local service
  for service in "$@"; do
    if [[ $service == journal ]]; then
      docker compose run --rm --no-deps -T journal uv run --frozen --no-dev alembic upgrade head
    fi
    docker compose up -d --no-deps --no-build --wait --wait-timeout 180 "$service"
  done
}

portal_proxy() {
  # Validate before touching the currently running nginx.
  docker compose run --rm --no-deps -T nginx nginx -t
  docker compose up -d --no-deps --no-build --force-recreate nginx
  docker compose exec -T nginx nginx -t
  local path
  for path in / /dude/api/health /journal/health /dude/auth/; do
    curl --fail --silent --show-error --connect-timeout 5 --max-time 20 \
      --retry 3 --retry-delay 2 --retry-all-errors \
      --resolve yoiwerr.site:443:127.0.0.1 "https://yoiwerr.site$path" >/dev/null
  done
  portal_ok 'HTTPS, dude, login page and Journal checks passed'
}
