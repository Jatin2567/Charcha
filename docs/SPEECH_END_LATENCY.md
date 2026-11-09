# Speech end to listener output

The project goal is **under 2,000 ms after source speech ends**, on a warm
service, with standard voices and meaning preserved. This is an engineering
target. The baseline uses standard voices with VoiceShield off. Record the
actual VoiceShield mode when measuring a monitored meeting and report it separately.

The saved 5,457 ms Hindi→Tamil and 7,489 ms Tamil→Hindi provider results start
before connecting/uploading their clips. Neither establishes this new boundary.
Do not subtract a clip's duration and call the remainder listener latency.

## Three separate measurements

1. **Source end → first decoded RTC audio:** a local synthetic source and receiver
   can share Python's monotonic clock. This exercises the real room, interpreter
   routing and codec using provider doubles. It measures no browser speaker or
   human speech quality and cannot unlock live language acceptance.
2. **Browser render estimate:** browser output timestamps may estimate scheduled
   rendering. This is still an estimate and does not prove acoustic output.
   Leave the value unknown when it is not measured.
3. **Source end → actual listener output:** capture source reference and listener
   output in **one recording clock**, preferably as two isolated channels, then
   review their sample positions. A single-phone acoustic recording is also
   supported with the limitations below. Never subtract two device wall clocks or align separate
   recordings by guessing when they started.

## Offline local transport check

Start `node scripts/local.mjs --screening-off` on the host. The launcher clears
provider credentials and uses a separate local ledger. Then inspect the plan:

```powershell
.\server\.venv\Scripts\python.exe scripts/measure_local_speech_end.py
```

Only `--run-local` connects to the loopback SFU and generates synthetic PCM; no
microphone, camera, cloud model or speech service is opened. Use a fresh output
path under `work/`. First-route and warm-route observations stay separate.
The known synthetic speech end is the final voiced source frame's playout
completion in the same process as the receiver. It is an SDK playout marker,
not a physical microphone event; decoding and event scheduling add uncertainty.
No estimated-render or physical-output value is fabricated from decoded PCM.

## Shared recording for actual output

Prefer a recorder/audio interface or a carefully configured stereo recording path:

1. Put an isolated source-speech reference on **left channel** and the listener's
   output on **right channel**, recorded simultaneously by one clock. Electrical
   loopback measures the output path at the selected tap; an acoustic pickup at
   the listener measures actual speaker sound. Document which tap is used.
2. Keep unrelated applications silent and prevent source/output crosstalk.
   Wear headphones or use isolated electrical paths. Do not record another
   person's audio without their agreement.
3. Export uncompressed two-channel PCM16 WAV at 8–96 kHz, at most 120 seconds.
4. Review the waveform and audio. Mark the **first sample after the last voiced
   source sample** and the **first sample of the translated listener output**.
   Noise or unrelated notifications must not become the target onset. Review
   numbers, names and negation separately for meaning.
5. Save annotations with the recording's exact SHA-256. Preserve unsuccessful
   attempts with `status: timeout` or `error`, and output onset `null`.

### One phone, without extra recording equipment

Use the phone or recorder you already have to record **one continuous acoustic
track** containing the source speaker and the listener device's translated
speaker output. Put it where both are clear in a quiet room. Keep only the
intended source microphone unmuted, mute the listener device's microphone, use
moderate speaker volume and silence notifications. Speak one complete phrase,
then wait for the translation. The voices must be distinguishable by listening;
avoid overlapping speech, echo and other sounds that could be mistaken for the
translation. No extra audio interface or paid recorder is required.

Export or convert that same recording locally to **mono PCM16 WAV**, without
changing playback speed or editing the two turns independently. Use the hash and
sample positions of the final WAV. Set `capture_kind` to
`acoustic_single_channel`; this kind alone requires one channel, using channel 0
for both reviewed positions. The existing isolated and browser capture kinds
still require two channels. Prefer isolated stereo when it is available.

Review the waveform **and listen** to mark the last voiced source sample and the
first translated listener sample. Mark capture/annotation review flags only
after doing that review; meaning review remains a separate judgement. The
analyzer only checks local signal consistency: it cannot identify which voice
made a sound, prove a recording's origin or separate crosstalk. Hardware and
provider provenance remain operator-attested. Preserve unclear or unsuccessful
attempts as failures; do not guess an onset. Negative offsets remain visible as
overlap evidence and do not pass the aggregate acceptance gate.

Example annotation shape (replace indices/hash and review flags after review):

```json
{
  "recording_sha256": "REPLACE_WITH_SHA256",
  "trial_id": "hi-ta-warm-01",
  "source_language": "hi",
  "target_language": "ta",
  "condition": "warm_route",
  "provider_kind": "live",
  "capture_kind": "acoustic_two_channel",
  "voice_mode": "standard",
  "screening_mode": "off",
  "status": "complete",
  "source_speech_end_sample": 48000,
  "listener_audio_start_sample": 96000,
  "capture_attested": false,
  "annotations_reviewed": false,
  "meaning_reviewed": false
}
```

For the phone workflow, replace `capture_kind` above with
`acoustic_single_channel` and provide the reviewed mono recording. For isolated
electrical output, use `electrical_loopback_two_channel`. Browser render recordings
use `browser_render_dual_channel` and do not qualify as physical output.
Capture/provider provenance is **operator-attested**; the analyzer cannot prove
that a file came from real hardware or a named provider.

Use `"screening_mode": "monitor"` for monitored rooms or `"enforce"` for rooms
that hold audio for screening. Older annotations without this field describe
the original screening-off baseline. In **Performance → Speech end → listener**,
choose **Open a playback observation** and select the resulting JSON. Only a
completed, operator-attested, reviewed live capture can be displayed as physical
playback. Importing reads metadata inside the tab and makes no upload.

```powershell
.\server\.venv\Scripts\python.exe scripts/measure_speech_end_playback.py --analyze --wav work/capture.wav --annotations work/capture.json --output work/observation-01.json
```

The analyzer computes `(output onset − source end) / sample rate × 1000`.
Negative offsets remain signed and need overlap review. Sample resolution is
not total measurement accuracy. No capture, API call or approval is performed.

## Optimization and expansion order

Optimize one Hindi→Tamil flow first. Review cold readiness separately and warm
Evon before starting a paid flow. Keep one recognition stream per speaker and
stream whole PCM samples immediately once the listener is ready. Preserve full
final text before translation so later negation is not spoken prematurely.
Do not shorten VAD silence or speculate on incomplete text without paired
meaning/segmentation trials. A small synthetic transport gain is not evidence
that the live cascade meets the target.

Prepare ten languages and ninety directed translation paths, but execute none
automatically. The language workflow requires ten independent reviewed warm
observations in the first direction, including failures, before considering
the reverse direction. Physical/electrical shared-clock evidence, live-provider
provenance, standard voices, meaning review and p50/p95 below 2,000 ms are needed
for the strict proposed gate. Both directions precede review of the remaining
88 paths. Passing a gate grants no API permission. Every paid test still needs
its own bounded approval; failed tests remain visible.

Sokuji's [streaming TTS design](https://github.com/kizuna-ai-lab/sokuji/blob/main/src/services/clients/SonioxTtsStream.ts) is a useful
reference for immediate audio delivery and explicit stream lifecycle. Its
provider capabilities do not establish Gnani support or this project's latency.
The implementation here is original; no Sokuji code is incorporated.

## Proposed first live canary — approval required

After the offline checks, prepare **one Hindi→Tamil turn**, with two Chrome
profiles on localhost and standard Tamil voice Trisha. The source speaker says
**“हम दस बजे मिलेंगे, ग्यारह बजे नहीं।”** once, within eight seconds. Only that
speaker's microphone is enabled. The listener stays muted and output remains
enabled. Stay silent after speaking; leave the source microphone on until the
translated output completes, because muting cancels pending output by design.
Do not repeat a failed phrase under the same grant.

Start the phone/shared recorder before the turn, following the capture steps
above. This gives the actual source speech end and translated speaker onset
on one recording clock. It also permits a free rehearsal with the known local
audio route before any model is enabled. Recorder and Chrome permissions are
user actions; this page never activates them automatically.

| Reviewed resource | Proposed maximum |
| --- | ---: |
| Active participants / source microphones | 2 / 1 |
| STT connections / reserved seconds | 1 / 25 |
| MT requests / source characters | 1 / 500 |
| Standard target TTS requests / characters | 1 / 300 |
| Source TTS / retries / voice enrollments | 0 / 0 / 0 |
| Operator grant | 180 seconds |

Request Prisma v3.0 explicitly. Keep the existing 600-ms finalization setting;
this first canary measures the current route before risking shorter pauses.
Apply `USAGE_STT_MAX_RETRIES=0` and `USAGE_REQUIRE_FLOW_APPROVAL=true` only to the
live-test process. Warm and verify Evon before issuing the short speech grant.
Use a room-scoped grant for the chosen meeting. Unmute only the intended test speaker.

At the supplied ₹27/hour STT and ₹27/10,000-character TTS rates, the ceiling is
**₹0.9975 reference**, excluding unverified rounding/taxes. Modal compute is
separate and must stay inside the existing $10 stage, with a fresh window of at
most 30 minutes and explicit shutdown immediately after the turn or failure.
No GCP server is needed. The following prints the local grant proposal only:

```powershell
.\server\.venv\Scripts\python.exe scripts/provider_flow.py plan --purpose live_interpretation --room-code MEETING_CODE --seconds 180 --stt-seconds 25 --stt-connections 1 --mt-requests 1 --mt-characters 500 --tts-requests 1 --tts-characters 300
```

Do not run `approve`, enable live processing or unmute a paid source before the
owner approves these exact limits. One canary is a diagnostic observation, not
p95 acceptance. Review its actual shared recording and meaning before preparing
the remaining warm observations. The other languages remain gated.

A future handshake optimization is bounded reuse of a Gnani TTS WebSocket.
The [official connection flow](https://docs.gnani.ai/api/TTS/tts-websocket) permits
another sequential synthesis request after the previous final response. This
reuse is not implemented or measured here. It would need bounded idle lifetime,
request ownership, cancellation/error cleanup and closure at flow expiry, while
preserving listener readiness, final text and existing request limits. Do not
infer a latency gain or introduce automatic paid retries from this reference.
