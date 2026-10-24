#!/bin/sh
# Offline configuration checks only. Never prints resolved Compose environment values.
set -eu
if [ "$(uname -s)" != Linux ]; then
  echo 'This host-network deployment requires a Linux server.' >&2
  exit 1
fi
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
command -v docker >/dev/null
command -v python3 >/dev/null
task_compose_version=$(docker compose version --short)
python3 - "$task_compose_version" <<'PY'
import re
import sys
parts = re.match(r"v?(\d+)\.(\d+)", sys.argv[1])
if not parts or tuple(map(int, parts.groups())) < (2, 30):
    raise SystemExit("Docker Compose 2.30 or newer is required for literal secret values.")
PY
python3 "$task_root/scripts/prepare_deployment.py" --check
docker compose -f "$task_root/deploy/production/generated/compose.json" config --quiet
echo 'Static configuration passed. DNS, TLS, firewall, media and provider access still require live checks.'
