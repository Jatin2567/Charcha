#!/bin/sh
# Explicit operator action: builds images, starts the stack and requests TLS certificates.
set -eu
task_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
sh "$task_directory/check.sh"
docker compose -f "$task_directory/generated/compose.json" up --build --detach
echo 'Stack started. Check HTTPS readiness and two-browser audio before considering it accepted.'
