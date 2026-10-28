#!/usr/bin/env bash
# Build only; never switch running application containers.
set -Eeuo pipefail
source "$(dirname "$0")/lib/deployment.sh"
portal_lock
portal_services "$@"
portal_config
portal_build "$@"
