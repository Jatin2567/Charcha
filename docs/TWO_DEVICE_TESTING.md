# Two physical devices without provider credits

This is the next original-audio acceptance test. It needs no GPU, Gnani key, Evon endpoint or voice cloning. The existing `npm run dev:local` remains loopback-only; do not copy its `127.0.0.1` URL to the second device.

After preparing the secure stack below, open **Test lab → Two-device audio**
(`#/tests?stage=device-check`) for the six free reliability scripts. Save only
real observations, export them before switching browser profiles, and keep the
workspace in original-audio mode. Completing the UI checklist does not install
certificates, change the firewall or automatically verify either device.

## Current laptop checkpoint — 28 October 2026

The actual prepared stack is `work/lan-20261028/compose.json`, for `192.168.1.7`.
Both application images built, all four containers started, the API became healthy,
both nginx configurations validated, and installed Python dependencies passed `pip check`.
HTTPS frontend/API and two authenticated WSS signaling joins passed with the public
CA explicitly supplied to the test client. That test changed no Windows trust settings
and did not negotiate WebRTC media or capture audio.

The owner clicked **No** on the Windows certificate-trust prompt. The certificate
was confirmed absent from `CurrentUser\\Root`; do not treat either browser as trusted.
Windows network profile and firewall rules were left unchanged. The second Windows
device's exact IPv4, trust installation and real listening are still needed.
The leaf certificate expires on **4 November 2026 at 17:00:24 IST**; regenerate it
if it expires or the laptop's IP changes. Transfer only the public `.cer` file.

To repeat the no-trust-change signaling check while the prepared containers run:

```powershell
.\server\.venv\Scripts\python.exe scripts/verify_lan_stack.py --manifest work/lan-20261028/manifest.json --ca work/lan-20261028/tls/ca.pem --output work/pre-gpu/lan-signaling-repeat.json --https-only
```

Use a new output filename each time. Omitting `--https-only` runs the synthetic
audio probe and requires normal native RTC certificate trust. Neither mode is a
substitute for two physical devices and human listening. The fixture memberships
are removed after the check, and evidence contains no membership credentials.

## Prerequisites

- Docker Engine running Linux containers and Docker Compose v2. Installation/downloads are separate; the preparation script installs nothing.
- Both devices on the same trusted Wi-Fi/LAN, with guest/client isolation off. Use headphones and preferably one person per device.
- The laptop's stable private IPv4 (for example `192.168.1.23`). A changed DHCP address requires a matching certificate and newly prepared configuration.
- A valid PEM server certificate whose **IP Subject Alternative Name** contains that exact address, its matching unencrypted private key, and its issuing CA certificate. Use the offline generator below or certificates from your network administrator. The IP must be an IP SAN, not just a certificate common name.
- Trust that issuer on each test device using its normal certificate-management flow. Transfer only the **public CA certificate** to the second device, never the server key or CA signing key. No browser certificate bypass or insecure-origin flag is needed or appropriate.
- Host firewall access limited to the two test devices on TCP **8443, 8444, 7881** and UDP **7882**, on the private network profile. Do not add router port forwarding or expose the stack to the Internet. Preparation makes no firewall changes.

The certificate/key match, certificate validity, chain and IP SAN are checked by an offline TLS handshake before writing. This does not prove that a browser trusts the issuer. No root certificate is installed automatically.

## Prepare first

The offline generator uses an existing OpenSSL executable (including the one bundled with Git for Windows). It installs nothing, makes no network call, and does not import a certificate or change a firewall. The server certificate lasts **seven days**, the issuer lasts eight days, and the exact IP is its only server SAN. The issuer has a critical name constraint for that IP, path length zero, and a one-use signing key that is discarded after generation. Private output uses a current-user Windows ACL or POSIX owner-only permissions. Regenerate in a new directory after expiry or an IP change; remove old trust after the test.

```powershell
.\server\.venv\Scripts\python.exe scripts/create_lan_certificate.py --ip 192.168.1.23 --output work/lan-tls
```

This creates public `charcha-lan-ca.cer` and `ca.pem`, server `cert.pem`, private server `key.pem`, and a non-secret manifest. It never retains the CA signing key. **Transfer only `charcha-lan-ca.cer` to the second device.** The server private key stays on the laptop hosting the stack.

Run from the repository root. Substitute the actual private address. The first command is a dry run, writes nothing and needs no certificate:

```powershell
.\server\.venv\Scripts\python.exe scripts/prepare_lan_test.py --ip 192.168.1.23
```

Once the certificate files exist, prepare a new private directory:

```powershell
.\server\.venv\Scripts\python.exe scripts/prepare_lan_test.py --ip 192.168.1.23 --write --certificate work/lan-tls/cert.pem --private-key work/lan-tls/key.pem --ca work/lan-tls/ca.pem --output work/lan
```

It copies the supplied TLS files and creates `compose.json`, `nginx.conf`, `livekit.yaml`, `api.env` and a non-secret `manifest.json`. It never reads your saved provider `.env`. Inspect the manifest, not private files, when sharing diagnostics. Keep all generated files under `work/`; do not publish that folder.

### Trust the public test certificate on both Windows devices

Use the paths and fingerprints from your generated manifest, and compare the fingerprint through a separate trusted channel before importing on the second device. In a normal PowerShell window under the same account that runs Chrome:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'C:/path/to/charcha-lan-ca.cer'
Import-Certificate -FilePath 'C:/path/to/charcha-lan-ca.cer' -CertStoreLocation Cert:\CurrentUser\Root
```

The SHA-256 must match `issuer_sha256` in the manifest. Windows' displayed certificate thumbprint uses SHA-1 as a store identifier and should match `issuer_windows_thumbprint`; the certificate itself is signed with SHA-256. Close and reopen Chrome if it was already open. This changes trust only for the current Windows account and should be removed afterward using the exact manifest thumbprint:

```powershell
Remove-Item -LiteralPath 'Cert:\CurrentUser\Root\EXACT_ISSUER_WINDOWS_THUMBPRINT'
```

Do not run this placeholder unchanged, delete other certificates, trust a different issuer or bypass a Chrome certificate warning.

### Limit firewall access to the other device

On the second Windows laptop, use `ipconfig` and copy the Wi-Fi IPv4 address. The server's Wi-Fi network must already be marked **Private** because it is your trusted home network. The script never changes that profile. Start with a dry-run plan; substitute both actual addresses:

```powershell
.\scripts\configure_lan_firewall.ps1 -LocalIp 192.168.1.23 -PeerIp 192.168.1.24
```

Review the two rule names, interface, four ports and exact allowed peer. In an **Administrator PowerShell** window, repeat with `-Apply`. Applying checks that the local IP belongs to the selected interface, that it is Private, and that the peer is on the same subnet. No Internet, router-forwarding, Public-profile or whole-subnet rule is added. If a named rule exists, inspect it rather than overwriting it. Remove only these rules after testing by repeating the command with `-Remove`.

Docker Desktop may have its own broader existing rules. This helper does not change or certify other rules. A second-device reachability test remains necessary; HTTPS success does not prove WebRTC audio.

## Start only when both devices are ready

Stop the current local launcher with Ctrl+C first to avoid competing media ports. These commands create only local containers; building can download dependency/container images. They do not start a cloud server or use speech-provider credits:

```powershell
docker compose -f work/lan/compose.json config --quiet
docker compose -f work/lan/compose.json up --build -d
docker compose -f work/lan/compose.json ps
```

Do not print the full resolved Compose configuration; use `config --quiet`, because resolved environments include local credentials. Do not use a shell `.env` override or change this stack to live mode.

Both browsers open **`https://192.168.1.23:8443/#/tests`**, using the actual address. Confirm there is no certificate warning and the UI reports **Raw audio test**. The media endpoint is `wss://192.168.1.23:8444`; signaling is proxied over TLS, while LiveKit advertises the LAN address for encrypted WebRTC media on TCP 7881 / UDP 7882. The API and unencrypted signaling ports are not published on the host.

The bridge-network configuration still needs an actual Docker/host acceptance test. In particular, Docker Desktop and host firewalls must allow the server participant and both browsers to reach the advertised media address. A successful HTTPS page load alone does not establish audio connectivity.

## Test and record outcomes

1. On laptop A, create a room as Asha, select Hindi and consent. On device B, join the invitation as Kavya and select Tamil. Keep microphones muted until both show **Audio connected**.
2. Enable speaker playback with a user click if prompted. A speaks: “The blue notebook is on the table.” B should hear the original sentence once. Language selections do not translate in this mode.
3. Reverse direction. B speaks: “Let us meet at the library tomorrow.” A should hear the original sentence once.
4. Mute A, wait for previously buffered audio to finish, then speak again. B must hear no new speech. Unmute and verify recovery. Repeat for B.
5. With separate headphones, speak briefly at the same time and check both directions. Check that each person does not hear their own returned voice.
6. Disconnect B's Wi-Fi briefly, restore it and use **Reconnect audio** if needed. Confirm participant and audio recovery without duplicated playback. Leave B and verify its card disappears and its audio stops.
7. While a call remains open, visit Performance in another tab on that same browser. Export transport/probe observations. For audible delay, record source and receiver markers on one consented shared timeline; do not subtract timestamps from different devices. Raw mode must not produce interpreted-speech latency samples.
8. Record pass/fail/blocked in Test lab with actual browser/device/headphone details. An automated tone or prepared configuration is not a human listening pass.

If certificates fail, correct issuer trust/IP SAN instead of bypassing browser checks. If the page loads but audio fails, check WSS access, the private-network firewall, client isolation, port conflicts and Docker media reachability. Do not expand exposure to the public Internet to work around a local routing failure.

## Stop the owned stack

```powershell
docker compose -f work/lan/compose.json down
```

This stops only the named local test stack and preserves its volume and private configuration. Do not add `--volumes` as a routine cleanup. Return to the laptop-only setup with `npm run dev:local` and create a new room. The local Audio lab remains available through that original launcher; this LAN baseline deliberately does not expose it.

Status: configuration preparation and offline tests can run before GPU access. Docker startup, certificate trust, device reachability, human listening and measured two-device latency remain acceptance checks until actually performed.
