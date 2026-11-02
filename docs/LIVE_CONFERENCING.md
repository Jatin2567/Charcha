# Live conferencing

The current delivery is standard-voice audio/video conferencing with language
routing, captions, invitations, device controls and recoverable connection
states. Local VoiceShield acoustic monitoring is working; its accuracy validation,
further latency reduction and voice cloning remain later work.
An under-two-second target is not a prerequisite for ordinary calls.

## Two normal launch profiles

For the optional working acoustic monitor, run `npm run dev:shield` instead of
the original-audio profile below. It uses the installed local CPU classifier,
reports real participant signals and leaves audio flowing. It makes no provider
calls. See [local VoiceShield testing](LOCAL_TESTING.md#working-voiceshield-microphone-monitoring).

```powershell
npm run dev:local
```

This starts self-hosted LiveKit, the API and the frontend at
**http://127.0.0.1:5180**. It carries original microphone audio and camera video.
Speech-provider clients and credentials are disabled. Use it for invitations,
devices, reconnects and local multi-person rehearsal without API credits.

```powershell
npm run dev:live
```

This starts the same stack with real provider adapters and standard voices.
It reads private configuration from `server/.env`; paid interpretation stays
locked until an operator approves a bounded flow. It never provisions a server,
deploys/warms a cloud model or grants itself credits. Screening, voice enrollment
and automatic recognition retries are disabled in this profile.

Check setup without starting services or making provider calls:

```powershell
node scripts/local.mjs --plan
node scripts/local.mjs --check
node scripts/local.mjs --live --check
```

Run only one stack on its ports. Ctrl+C stops the launcher's owned children.
Development LiveKit keys apply only to loopback; use the production generator
for internet hosting.

## Live configuration

| Setting | Purpose |
| --- | --- |
| `GNANI_API_KEY` | Existing Gnani STT/TTS access |
| `GNANI_STT_MODEL=prisma-v3.0` | Explicit streaming recognition model |
| `EVON_BASE_URL` | Running OpenAI-compatible inference endpoint, including `/v1` |
| `EVON_MODEL` | Exact served model name |
| `EVON_API_KEY` | Server-only inference key, when required |
| `EVON_MODAL_KEY` / `EVON_MODAL_SECRET` | Server-only proxy authentication for HTTPS Modal hosts |
| `TIMBRE_MODEL=timbre-v2.5` | Standard speech synthesis model |

The launcher supplies its own local LiveKit configuration. Language-specific
voice overrides are optional; the v2.5 stock catalog provides matching defaults.
Configuration presence does not prove an endpoint is online or an account has
voice entitlement.

Optionally use an existing ignored Modal client file without putting its values
in shell arguments, the frontend process or the browser:

```powershell
npm run dev:live -- --evon-base-url https://YOUR_OWNED_HOST.modal.run/v1 --evon-model gnani/gnani-evon-v3.3-30B-A3B --evon-client-file work/modal-private/client.json
```

The file contains exactly `api_key`, `modal_key` and `modal_secret`. The launcher
validates the destination and keeps values private. It does not start Modal.
An available, separately approved model service is still required.

## Join and talk

1. In normal Chrome create a conversation, choose your name and language,
   consent and join. Microphone and camera start off.
2. Copy **Invite people** into Incognito or another browser profile. Join with a
   separate name and language. Use the invitation's join link, not a duplicated
   joined-call tab.
3. Confirm connected audio. Click **Enable speaker** if browser playback needs
   a gesture. Select devices before talking. Camera sharing is optional.
4. In original-audio mode, unmute intentionally and test both directions with
   headphones. This makes no speech-provider calls.
5. Live mode explains whether interpretation is waiting for configuration,
   operator permission or capacity. Same-language forwarding and an otherwise
   empty room need no paid recognition session. Different-language listeners
   require sufficient approved allowances.
6. When permitted, unmute and speak a short complete phrase. Your language sets
   recognition and listening. Standard-voice translations replace the original
   track for different-language listeners; original tracks remain interpreter-only.
7. Use captions/transcripts, invite more participants and change language.
   Reconnection, microphone changes and device loss require deliberate capture
   re-enabling. Mute and leave stop hardware.
8. Leave explicitly. Save a recap only if you want browser-local history.

### Read captions during a call

In an interpreted room, captions appear above the call controls in your listening
language. Each line names the speaker. While a translation is pending, its line
shows the labelled original and updates when the translation arrives. Scroll
back to read earlier turns and select **Latest** to resume following. **Large
text** saves your preferred size on this browser. The **Captions** button or
**C** hides and shows the panel. Try the scripted demonstration for free.

### Invitation and call-status guidance

The invitation button opens Room details first for a localhost or HTTP address.
It explains the link's limits before **Copy same-computer link** or **Copy current
test link** is offered. No replacement LAN address is guessed. A non-loopback
HTTPS invitation still needs actual device, certificate and media checks.

Expand **Call setup & approved allowance** to see media connection, configuration,
remaining resource units and operator renewal steps. Model availability stays
**Not checked**: this panel never probes or wakes Evon. Approved-flow time is
estimated from the server's snapshot clock and elapsed browser time; the server
remains authoritative when admitting speech. Missing configuration, expired
approval and exhausted allowances have distinct messages. Unknown units are
shown as unavailable, never as zero, and no rupee charge is inferred.

The free device checklist is at **Test lab → Two-device audio**, or
`#/tests?stage=device-check`. Six manual scripts cover permissions, five-minute
playback, network reconnection, camera release, overlapping original audio and
microphone changes. Observations can be saved and exported without opening a
device or contacting a speech provider. Results start as **Not tested**. Use the
original-audio LAN stack and complete the trusted-HTTPS setup before these checks;
the localhost launcher cannot serve a second computer.

Ten configured choices are Hindi, Tamil, Bengali, English, Telugu, Kannada,
Malayalam, Marathi, Gujarati and Punjabi. All 90 directed routes use the same
pipeline. Routing support does not prove equal language quality: Hindi↔Tamil has
controlled provider evidence; other routes still need live speech/meaning checks.
Ten languages do not imply ten simultaneous recognizers. Admission limits and
remaining budgets are enforced separately.

## Provider permission and recovery

The browser and HTTP API cannot approve a flow. Review `provider_flow.py plan`,
obtain human approval, then use the local-only `approve --human-approved` command
with those exact budgets. Close the grant afterward. Daily caps, concurrency and
atomic reservations remain the final gate when browsers unmute concurrently.

Allow one MT/TTS request per **distinct other listener language**, not per
listener. Shared target languages share output. No-listener/same-language audio
uses no STT/MT/TTS. A new source needs a remaining STT connection; an ongoing
connection is not mistaken for a missing allowance. Muting is always available.

Ordinary calls do not depend on a temporary canary controller or expiring manual
model-ready handoff. The UI separates configuration and permission from actual
provider validation. Provider failures remain visible; no scripted translation
or automatic paid retry replaces them.

## Verification and future modules

Local checks cover room isolation, recipient routing, shared targets, camera
grants, PCM delivery, device lifecycle, playback recovery and usage enforcement.
Provider doubles validate control flow without claiming language accuracy.

**Latency:** retain existing measurements in Performance/Test lab with their
boundaries. Shared-recording optimization is optional later research.

**Deepfake detection:** retain the experimental service boundary and Audio lab
for future work. Normal calls keep screening off and make no verified detection
or automatic protection claim.

**Voice cloning:** retained adapters/research are separate; conference launch
profiles perform no enrollment or cloned synthesis setup.

For two devices see [TWO_DEVICE_TESTING.md](TWO_DEVICE_TESTING.md). For hosting
see [production setup](../deploy/production/README.md). HTTPS, UDP/TURN and an
accessible inference service require checks on the actual host; local tests do
not establish a deployed service.

## Local delivery checks — 30 October 2026

The shared visual layer is `web/src/theme.css`. It defines workspace surfaces,
primary teal, success/attention/error tokens and the dark call palette. Report
styles use the same supporting-text tokens. Call buttons have explicit visual
state attributes, icons, labels and pressed semantics; disabled controls retain
readable text with dashed borders. These presentation states do not authorize
capture, approve a flow or change speech processing. Selected foreground/background
pair checks are saved in `work/local/ui-palette-20261030.json`; they are not a full
accessibility audit. The Developer journal records the colour changes and limits.
The colour-update frontend run is `work/local/frontend-palette-20261030.log`;
workspace and call screenshots are `palette-workspace-20261030.png` and
`palette-call-20261030.png` in that directory.

- Frontend: **258 tests passed**, with TypeScript and the production build passing.
- Backend: **1,271 passed, one skipped**. Final readiness wording also passed its
  24 focused checks. The only full-suite warning is a TestClient deprecation.
- Launcher: **six checks passed**, including credential isolation, no-read
  planning and provider-flow locks. Both setup preflights made zero provider calls.
- Real loopback RTC with provider doubles: **six peers, five sequential sources,
  20 translation branches, 25 first-audible recipient routes and five camera
  receivers passed**. Final fixture runtime was 122.793 seconds, with no structured
  cleanup failures. This duration includes the whole fixture and is not speech
  latency. A late SDK publisher negotiation warning after close is retained.
- Browser UI: two muted members joined through normal invitations, reconnected
  with capture off and left cleanly. In live mode, the Hindi/Tamil pair saw the
  operator-approval message and disabled unmute. No microphone/camera permission,
  provider approval or cloud-model launch was performed.

Local artifacts are under `work/local/`: `conference-five-language-final-20261030.json`,
`backend-conference-final.log`, `frontend-invitation-status-final-20261030.log` and
`conference-live-ui-20261030.png`. Private account/configuration files are excluded.
The Developer journal records the remaining real-device, sustained-playback,
simultaneous-speaking and live-language acceptance checks. The build reports
large JavaScript chunks; bundle splitting can be evaluated separately.

On this Windows execution environment, tests needed a writable temporary folder
inside the workspace. Async Python fixtures also required local-loopback access;
the restricted default blocked event-loop socket creation before a test body.
Neither issue required changing product behavior.
