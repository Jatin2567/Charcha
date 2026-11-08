# India-hosted identity for Charcha

The server supports Keycloak as an OIDC provider using authorization code, PKCE, nonce, state, signed RS256 ID tokens and verified email. Run Keycloak and PostgreSQL in the selected India region. Google still handles Google account authentication upstream. Check logs, backups and provider settings separately before claiming end-to-end data residency.

The accompanying `compose.yaml` is prepared for the same Linux host as the meeting stack. It binds Keycloak only to loopback port 8180 and leaves PostgreSQL private. The production web proxy forwards `/identity/` over HTTPS. Public `/identity/admin/` access is blocked. Perform realm administration through an SSH session using Keycloak's `kcadm.sh` inside the container. No identity container has been started by this preparation.

## Operator inputs

- A stable HTTPS application origin on a domain you control, plus the existing LiveKit/TURN DNS names and public media-capable host.
- A private `deploy/identity/.env`, copied from `identity.env.example`. Choose separate database and bootstrap administrator passwords. Set a random client secret matching the API environment. Enter all values directly in the private files.
- A Google OAuth web client with only `openid email profile` access. Register the callback `https://YOUR_APPLICATION_HOST/identity/realms/charcha/broker/google/endpoint`. In Google testing mode, explicitly allow the test accounts. Public launch needs the appropriate Google publishing/verification checks. Do not request Gmail or Drive access.

## Configure the realm

The import file uses environment placeholders for the application URL and OAuth secrets. The first import creates the `charcha` realm and confidential `charcha-web` client. Imports do not overwrite an existing realm on restart. Apply later changes deliberately in Keycloak and preserve its PostgreSQL volume.

After host, DNS and deployment approval are ready, validate with `docker compose --env-file deploy/identity/.env -f deploy/identity/compose.yaml config --quiet`, then start that stack explicitly on the server. Realm administrator credentials must be entered by the operator. Provision the Charcha application administrator as a local Keycloak user, verify its email, complete OTP enrollment and record its immutable realm user ID.

Map actual successful password and OTP executions to `pwd` and `otp` authentication references using Keycloak's authentication-flow controls. The bundled AMR mapper adds these proven references to the ID token. The API requires both references, the designated administrator's exact subject and a fresh `auth_time`. It fails closed if the flow or enrollment is incomplete. A hard-coded MFA claim must never be used.

Set the API's private environment before preparing the transport-mode stack:

```dotenv
CHARCHA_IDENTITY_PROVIDER=keycloak
CHARCHA_PUBLIC_ORIGIN=https://YOUR_APPLICATION_HOST
CHARCHA_OIDC_ISSUER=https://YOUR_APPLICATION_HOST/identity/realms/charcha
CHARCHA_AUTH_CLIENT_ID=charcha-web
CHARCHA_AUTH_CLIENT_SECRET=ENTER_THE_SAME_PRIVATE_CLIENT_SECRET
CHARCHA_MEETING_HOST_EMAIL=ENTER_THE_VERIFIED_HOST_EMAIL
CHARCHA_ADMIN_SUBJECT=ENTER_THE_LOCAL_ADMINISTRATOR_USER_ID
```

For this project the designated meeting host is the owner's verified main email. Public Google users may ask to join. The host remains the only account allowed to create meetings, and each room retains host-controlled admission.

## Acceptance

Verify the issuer's discovery document resolves over trusted HTTPS and reports the exact configured issuer. Then test Google sign-in with two distinct users, rejection of unverified email, host-only room creation, admission and denial, and sign-out. Test the separate local administrator with password and OTP. Confirm a password-only token fails. Finally verify original audio from two physical devices before authorizing speech providers.

Local automated checks cover signed token verification, realm endpoint selection and administrator MFA rejection. A real Google login, Keycloak realm import, OTP enrollment and India-hosted meeting still require verification on the selected server.

[Keycloak containers](https://www.keycloak.org/server/containers), [realm import](https://www.keycloak.org/server/importExport), [OIDC endpoints](https://www.keycloak.org/securing-apps/oidc-layers), [AMR mapper](https://www.keycloak.org/admin-api/protocol-mappers)
