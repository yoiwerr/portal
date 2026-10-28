#!/usr/bin/env bash
# First installation only. Existing servers use update.sh.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then
  printf '[ERROR] Create .env from .env.example and fill credentials and model settings first. Existing files must be preserved.\n' >&2
  exit 1
fi
exec ./scripts/update.sh --initial "$@"
