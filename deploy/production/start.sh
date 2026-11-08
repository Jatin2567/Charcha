#!/bin/sh
# Explicit operator action: builds images, starts the stack and requests TLS certificates.
set -eu
task_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
sh "$task_directory/check.sh"
for setting in CHARCHA_AUTH_CLIENT_ID CHARCHA_AUTH_CLIENT_SECRET CHARCHA_ADMIN_SUBJECT CHARCHA_MEETING_HOST_EMAIL; do
    grep -Eq "^$setting=.+" "$task_directory/generated/api.env" || { echo "Missing sign-in setting $setting"; exit 1; }
done
if grep -q '^CHARCHA_IDENTITY_PROVIDER=keycloak$' "$task_directory/generated/api.env"; then
    grep -Eq '^CHARCHA_OIDC_ISSUER=.+/realms/.+' "$task_directory/generated/api.env" || { echo 'Missing identity realm issuer'; exit 1; }
else
    grep -Eq '^CHARCHA_AUTH_DOMAIN=.+' "$task_directory/generated/api.env" || { echo 'Missing Auth0 domain'; exit 1; }
fi
docker compose -f "$task_directory/generated/compose.json" up --build --detach
echo 'Stack started. Check HTTPS readiness and two-browser audio before considering it accepted.'
