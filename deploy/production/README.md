# Single Linux VM deployment

This prepares the frontend, one API/RTC worker, open-source LiveKit and Caddy on one India-region Linux VM. It uses your own LiveKit credentials and does not require a LiveKit Cloud account. Evon inference remains a separate, approved OpenAI-compatible endpoint; this CPU stack does not download or run a 30B model.

The preparation step is offline. It does not provision a VM, modify DNS/firewalls, start containers, request certificates or spend provider credits. The current delivered evidence covers generated configuration and tests. Real DNS, certificates, restrictive-network TURN and Gnani/Evon access require acceptance on your actual server.

For the current standard-voice pilot, see
[the 30 October conference stage](../../docs/CONFERENCE_STAGE_ONE.md). It keeps
screening off and cloning deferred. When using the authenticated Modal endpoint,
the private input environment can supply `EVON_MODAL_KEY` and
`EVON_MODAL_SECRET` alongside the separate `EVON_API_KEY`. The generator preserves
that complete pair only for an HTTPS `*.modal.run` destination on port 443; it
rejects incomplete/unsafe pairs before writing deployment files. Per-language
`TIMBRE_VOICE_HI/TA/BN/TE/MR` overrides are preserved too. None of these credentials
belongs in the browser bundle.

Use `USAGE_VOICE_ENROLLMENTS_PER_DAY=0` for this stage. The two-person speech
check keeps existing admission defaults; five active microphones require an
explicitly reviewed `USAGE_MAX_CONCURRENT_STT=5` and measured operation/queue
capacity within the provider's limits. Five language selections do not prove
that five simultaneously speaking participants have passed acceptance.

## Inputs from the owner

- A Linux VM with a stable public IPv4 and inbound TCP/UDP control. Start with 4 vCPU, 8 GB RAM and 40 GB disk for a small pilot, then size from measurements; this is a starting estimate, not a tested capacity guarantee. No GPU is needed here when Evon runs elsewhere.
- Three DNS names you control, for example `meet.your-domain.in`, `rtc.your-domain.in` and `turn.your-domain.in`, all resolving directly to that VM. Disable HTTP-only/CDN proxying for these names and remove conflicting AAAA records unless IPv6 is deliberately configured.
- Working Gnani credentials with STT, Timbre and optional voice-enrollment entitlements.
- The actual Evon base URL, served model ID and authentication key, if required. A Gnani closed-beta endpoint is usable only after access approval and confirmation that its request/response contract matches this adapter. Otherwise provide a trusted GPU-hosted endpoint. Do not guess an endpoint or assume STT credits cover hosted MT.
- An approved daily usage budget. Conservative limits are copied from the private server environment file; zero disables the relevant resource.

## Prepare

Prefer generating directly on the deployment server so secrets do not need to be transferred from Windows. Use Python 3.12 and Docker Engine with Docker Compose **2.30+** installed through your host/provider's supported instructions. The scripts do not install software or change the firewall.

1. Copy the source checkout to the server. Copy `server/.env.example` to the ignored `server/.env`, then enter the Gnani and Evon values there. Only one-line values are supported; optional enclosing single/double quotes are stripped without variable interpolation. Keep this file private. Leave the LiveKit values blank: the generator creates a fresh matching key pair.
2. Copy `deploy/production/inputs.example.json` to a local JSON file. Replace all four domain/IP placeholders. This JSON contains no credentials. `caddy_image` defaults to LiveKit's official `latest` tag; for reproducible releases, replace it with an official image digest after verifying that release. LiveKit is pinned to the locally exercised `v1.9.1`.
3. From the checkout root, run:

```sh
python3 scripts/prepare_deployment.py --config deploy/production/inputs.json --env-file server/.env
sh deploy/production/check.sh
```

The output is `deploy/production/generated/`: `compose.json`, `caddy.json`, `livekit.yaml`, `api.env`, and a non-secret manifest. The entire directory is ignored and excluded from source archives and Docker build contexts. It contains real credentials. On Linux, the directory is mode 0700 and its files are mode 0600. Windows does not provide equivalent POSIX permission enforcement; check ACLs before moving a generated stack.

An existing output is never overwritten and keys are never silently rotated. Preserve its files for restarts. For a separate deployment, use a different `--output` directory and adapt the operator commands to that path. The bundled check/start scripts intentionally target the default `generated/` directory. Editing provider limits in `api.env` is supported within validated bounds; do not edit generated topology files. The literal Compose environment format preserves `$` and quote characters in secrets.

## Network and TLS

| Inbound port | Purpose |
| --- | --- |
| TCP 80 | ACME HTTP certificate issuance |
| TCP 443 | HTTPS, LiveKit signaling and TURN/TLS, selected by SNI |
| TCP 7881 | Encrypted WebRTC TCP fallback |
| UDP 3478 | Embedded TURN/UDP and STUN |
| UDP 50000–60000 | Direct encrypted WebRTC media |
| Your SSH port | Restrict to the operator's IP/network |

Do **not** expose TCP 5349: LiveKit expects plaintext TURN behind Caddy's TLS termination there. This port binds all interfaces in LiveKit 1.9.1, so a default-deny host firewall and provider security group must block it. API 8000, web 8080 and LiveKit signaling 7880 bind loopback; keep them closed in both firewalls as well. The scripts deliberately do not change firewall rules or risk locking out SSH.

Permit the required outbound DNS, HTTPS to registries/ACME/Gnani and your trusted Evon endpoint, and media traffic to participants. LiveKit receives an explicit public node IP and uses its own TURN server for STUN rather than relying on default public Google STUN discovery. The VM/provider must support a correct public-address mapping and UDP; an HTTP-only platform is unsuitable for this stack.

Caddy's official layer-4 module terminates TLS on TCP 443, then forwards the three hostnames to loopback ports 8080, 7880 and 5349. Ordinary Caddy/nginx HTTP reverse proxies cannot replace this shared-port TURN configuration. Certificates persist in a named volume. The stack does not promise a normal HTTP landing page on port 80; open the HTTPS application URL.

## Start and accept

After the DNS and firewall configuration is ready, the explicit operator start command is:

```sh
sh deploy/production/start.sh
```

This builds/pulls images and lets Caddy request certificates. It starts one API worker because rooms and RTC agents are process-owned. The API's daily reservation counters persist in the `artha-mesh-usage-ledger` Docker volume; do not delete that volume to reset a limit. The frontend is built in live mode, with same-origin `/api` and no browser-demo fallback.

Then verify the HTTPS application, `/api/health`, `/api/readiness` and `/api/usage`; none of those endpoints performs paid inference. Check the performance page after one deliberately short two-browser test. Confirm both normal UDP audio and a separate TURN/TLS test on a restrictive network. A configured key does not prove entitlement, latency or translation quality. Use a brief opt-in voice enrollment only if the owner has enabled that feature. Keep provider-side caps enabled as an additional boundary.

For updates, back up the private generated configuration and ledger first, review changes, then run the explicit start command again. Restarting the single API process ends its in-memory rooms; existing sessions must rejoin. This is a small pilot deployment, with no high availability, durable room store, SSO or multi-worker scaling. `docker compose -f deploy/production/generated/compose.json down` stops the stack while keeping named volumes. Do not add `--volumes` unless intentionally deleting persisted data and certificates.

## References and attribution

The Caddy layer-4 configuration shape and TURN topology are adapted from the Apache-2.0-licensed [LiveKit deployment generator](https://github.com/livekit/deploy), reviewed at commit `1a7b369f94e3a2f890d366fceeb4f273bf9fb3f6`, especially [the Caddy template](https://github.com/livekit/deploy/blob/1a7b369f94e3a2f890d366fceeb4f273bf9fb3f6/generate/templates/caddy.go) and [production settings](https://github.com/livekit/deploy/blob/1a7b369f94e3a2f890d366fceeb4f273bf9fb3f6/generate/production.go). Copyright LiveKit, Inc. The complete upstream license and NOTICE are included in `third-party/`, along with source provenance. Adaptations here add the application hostname, loopback signaling/API, explicit node IP, generated secret files and persisted credit ledger.

See also LiveKit's [VM deployment guide](https://docs.livekit.io/transport/self-hosting/vm/), [firewall guide](https://docs.livekit.io/transport/self-hosting/ports-firewall/) and the [1.9.1 TURN implementation](https://github.com/livekit/livekit/blob/v1.9.1/pkg/service/turn.go). The shared TLS port is advertised to participants as 443 by the [1.9.1 room manager](https://github.com/livekit/livekit/blob/v1.9.1/pkg/service/roommanager.go).
