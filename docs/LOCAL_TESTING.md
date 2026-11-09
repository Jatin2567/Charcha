# Local testing, before deployment

## Working VoiceShield microphone monitoring

Run `npm run dev:shield` from the repository, then open
`http://127.0.0.1:5180/`. This starts local LiveKit, the room API and the web
interface with the installed CPU AASIST detector in monitor mode. Provider
credentials are cleared and speech-provider clients are disabled in this mode.

Create a conversation, join with your microphone off, and open **VoiceShield**.
It reports detector readiness and the 4,037.5 ms audio window. Unmute and speak
for at least five seconds. Actual waveform assessments update the participant
badge and panel. A model flag displays a warning and a review action. A second
browser profile can join the invitation to check the same events as a listener.
Use headphones when testing both microphones.

The result contains an uncalibrated spoof score, analysis time and queue time.
Monitor mode forwards speech while classification runs. Muting or leaving clears
the active result, and disconnected event streams suppress current warnings.
Exports contain observations and model metadata. Accuracy and physical playback
impact remain pending validation. Existing human-only pilot results, including
false alarms, remain available in Audio lab and Performance.

The detector consumes original 16 kHz mono audio. Its inputs contain no transcript
or keyword search. The pinned AASIST model originates outside India and runs on
the host CPU. Startup verifies its checksum and never downloads model weights.

The October 31 functional checks used generated tones, the installed ONNX model,
real local WebRTC, room events and the browser. They verified alert delivery,
mute cleanup and zero provider usage, without establishing speech accuracy.

The 29 October [screening latency experiment](SCREENING_LATENCY.md) measured two CPU threads as faster on this laptop. The local launcher now uses that setting while retaining all 64,600 samples and the experimental thresholds; deployed defaults stay one thread. Performance and Audio lab show the saved comparison. Short-prefix experiments cannot release meeting audio, and real-speech accuracy remains unverified.

## Preparation while GPU access is pending (28 October 2026)

The Test lab now includes an exportable pre-GPU plan. Start with original audio;
voice cloning stays deferred. The following guides and tools run without provider
credits:

- [Two physical devices](TWO_DEVICE_TESTING.md): offline TLS/configuration preparation,
  followed by a separately started raw-audio LAN stack. Docker builds and explicit-CA
  HTTPS/WSS signaling passed. Windows certificate trust was deferred by the owner;
  device firewall access and actual listening remain pending. Never share a `127.0.0.1` invitation with
  another physical device.
- [GPU text test](GPU_TESTING.md): `server/.venv/Scripts/python.exe scripts/evon_benchmark.py`
  prints a two-request Hindi/Tamil plan without connecting. GCP/Yotta execution
  requires approval for that exact plan. It neither starts a VM nor spends Gnani
  speech credits. Standard-voice speech testing is a separate later flow.
- [Detector evidence](../evaluation/audio_screening.md): `--validate-only` checks
  declared consent, labels, duplicates and evaluation splits without inference.
  `--strict-manifest` requires those checks before local CPU scoring. Real labelled
  recordings must be supplied; no accuracy is inferred from existing tones.

Performance now offers grouped server-timing exports that separate direction,
microphone/text input and voice. They retain failed and cancelled attempts and
missing timing counts. They do not mix scripted or original-audio observations
with interpretation percentiles, or measure physical playback.

## Local screening and receiver timing (27 October 2026)

`npm run dev:shield` starts original audio with **monitor** screening. `npm run dev:local` starts with screening off. Both clear provider credentials for child processes. Open `http://127.0.0.1:5180/#/audio-lab`. This lab is opt-in, restricted to local demo/transport mode and loopback clients, rejects foreign browser origins, requires consent and retains no audio on disk.

1. Choose Silence, Steady tone or Clipped signal, tick local processing consent, then Analyze locally. These are diagnostic fixtures, not labelled speech or accuracy evidence.
2. For real speech, supply consented mono 16 kHz 16-bit PCM WAV, at most 30 seconds. The classifier consumes complete 64,600-sample windows (4,037.5 ms). Unscored tails are disclosed; short, silent, clipped, unsupported or uncertain audio never verifies a human.
3. Inspect the uncalibrated score, provenance/checksum, diagnostics and compute time. Export only when desired. Audio and filenames are excluded; refresh discards tab-local results.
4. In an active local room, open Settings → Receiver latency probe → Play receiver test tone. This sends a one-second tone only to you. Leave the microphone off. Performance shows request-to-decoded-tone p50/p95 and failures. One browser clock includes request/setup/buffering/polling; this does not measure microphone capture, translation or physical speaker output.
5. For source-to-listener delay, record both positions on one consented shared timeline and annotate Audio lab. Compare the same marker onset for raw audio; phrase-end to translated-audio onset is for later approved translation tests. Never subtract different device clocks.

Install the optional CPU runtime using `uv sync --project server --extra dev --extra screening --frozen`, then explicitly run `scripts/fetch_audio_screening_model.py` with the server Python. Startup never downloads a model. Omitting `--extra screening` in a later exact sync can remove ONNX Runtime. NAVER AASIST is foreign-origin and runs locally; India execution does not make it Indian-trained. Indian-language, replay/noise and unseen-generator accuracy is unverified.

To compare gating, stop the launcher and run `node scripts/local.mjs --screening-enforce`. This experimental mode releases only low-score complete windows, adds collection plus queue/compute delay and discards unknown, incomplete trailing, overloaded or failed windows. It can reject genuine speech. Use `npm run dev:local` for an unscreened baseline and `npm run dev:shield` to return to monitor. These modes do not establish liveness.

With local LiveKit running, execute these zero-provider checks:

```powershell
.\server\.venv\Scripts\python.exe scripts/verify_screening_transport.py
.\server\.venv\Scripts\python.exe scripts/verify_screening_transport.py --actual-model-monitor
.\server\.venv\Scripts\python.exe scripts/verify_audio_screening.py
```

The first checks gating mechanics with controlled verdicts, the second runs the real local model in monitor mode and the third measures isolated CPU work. Generated tones are excluded from speech accuracy. Estimated hold adds input-window duration to screening elapsed time and excludes receiver playback. CPU load materially changes screening and RTC delays.

Start with two browser profiles on this computer. Verify original audio first, then standard-voice interpretation, a second device and the hosted interface. Review three-person interpretation and voice cloning only after those gates pass. The detailed scripts and expected meanings are in [TEST_FLOWS.md](TEST_FLOWS.md); the interactive checklist is `/#/tests`.

## Start the original-audio test

From the project directory in PowerShell:

```powershell
# Initial setup, or after dependency changes:
.\scripts\setup.ps1 -Screening
.\scripts\setup-livekit.ps1

# Every time you want to start the local audio test:
npm run dev:local
```

The pinned LiveKit executable is downloaded from its [official release](https://github.com/livekit/livekit/releases/tag/v1.9.1) and checked against the verified Windows executable checksum. It is kept in ignored `work/bin/`. On macOS/Linux install that release's appropriate binary and set `LIVEKIT_BINARY` to its absolute path. No media-server binary is committed or included in a source archive.

The launcher checks local ports, starts LiveKit, waits for the API to report transport mode, and starts the web interface at **http://127.0.0.1:5180/#/tests**. It prints the selected API port, normally 8000, with 8100/8200 as alternatives. Set `CHARCHA_WEB_PORT` or `CHARCHA_API_PORT` in the shell when needed. It refuses to stop an unrelated process occupying a port.

The frontend, API and LiveKit signaling bind to loopback. LiveKit selects usable local-interface media candidates, with loopback and browser mDNS support enabled. Its development media credentials are suitable only for this local test. The saved `server/.env` remains unchanged; the launcher clears provider credentials for its child processes. Transport mode never constructs the Gnani/Evon clients, rejects interpretation and enrollment, and exposes no translated-caption or interpretation-latency result. All media goes through the local agent so source routing and mute enforcement are exercised.

Use Ctrl+C in the launch terminal to stop this stack. Leave only one launcher running at a time. Restarting clears ephemeral rooms/memberships; create a new room.

## Exactly two Chrome users on one Windows computer

One person can run this initial two-session check on one computer. Use **one normal Chrome window for A and one Incognito window for B**. Open Incognito with **Ctrl+Shift+N**. Follow this normal/private pairing rather than opening two Incognito windows, which share a private profile and preferences. Two ordinary tabs can also share saved preferences and are easier to confuse. You can use two separate Chrome profiles instead.

1. **A: create the room.** In normal Chrome, open **http://127.0.0.1:5180/**. Check the **Raw audio test** label. Click **New conversation**, enter **Asha** under **Your name**, choose Hindi, tick the conversation-processing consent box and click **Join conversation**. Keep the microphone off.
2. **A: wait for media.** Wait for **Audio connected** in the room. The top **Room connected** label refers to room events; by itself it does not establish a working audio connection. If necessary, open meeting **Settings**, use **Reconnect audio**, then wait for **Audio connected**.
3. **B: join the same room.** Click **Copy invitation** in A's room. Paste that invitation into the Incognito address bar. Enter **Kavya**, choose Tamil, tick consent and click **Join conversation**. Keep B muted too. Both rooms should show two participants and **Audio connected**.
4. **Prepare playback.** Use headphones rather than the laptop speakers. In each room, open meeting **Settings** and click **Enable speaker** if playback needs a user gesture. Under workspace **Settings → Microphone & speaker**, choose the intended input/output if the system default is wrong. Do not leave a separate microphone-test recording active during the call.
5. **A → B.** Keep B's microphone muted. Turn A's **Speaker** off and leave B's **Speaker** on. Click **Unmute** in A's room and allow Chrome's microphone prompt for this local site. Say: “Hello, can you hear me clearly? The blue notebook is on the table.” You should hear that original speech through B. Turning B's **Speaker** off should silence that playback; turn it back on afterward.
6. **Self echo and mute enforcement.** While A is speaking, turn B's **Speaker** off and A's **Speaker** on: there should be no returned or duplicated playback of A. Restore A's Speaker off/B's Speaker on. Click **Mute** in A's room, allow any already buffered audio to finish, then say: “This sentence should not be sent.” B should hear no new speech. Unmute A, say “The microphone is back on,” and confirm B hears it again. Mute A before the reverse test.
7. **B → A.** Turn A's **Speaker** on and B's **Speaker** off. With A muted, click **Unmute** in B's room and allow Incognito's separate microphone prompt. Say: “Yes, I can hear you. Let us meet at the library tomorrow.” A should hear B's original speech once. Repeat B's mute/unmute check, then mute B.
8. **Leave and clean up.** Click **Leave conversation** in B, then confirm **Leave conversation** in the dialog. B's participant card should disappear from A, with no new output from B. Leave A when finished.
9. **Record the result.** In Test lab, select **Local audio**, then record **Say hello, then reply** and **Mute, resume and leave** as pass, fail or blocked based on what you actually heard. Add the Chrome version and input/output devices; export observations before changing browser profiles. Keep the call open when using Performance in another tab. Raw mode should produce **no interpreted-speech timing samples**.

With one microphone and one headset, keep **only the current speaker unmuted**. Your own voice heard through the other participant's window is the expected A→B or B→A route, not proof of self echo. The receiver's Speaker toggle identifies which window is playing it. A proper two-person listening check is still required; one-person testing cannot judge two independent people speaking simultaneously. If another application holds the microphone exclusively, close that application's call or choose another input device; do not change browser security, firewall or certificate settings.

Hindi/Tamil selections deliberately do **not** translate anything in this mode. The listener hears the original language and voice. Captions and cloning are disabled. Use only **`npm run dev:local`** for this test, with no provider approval, API key entry or live-mode switch. To restart later, stop the previous launcher with Ctrl+C, run that same command and create a fresh room.

### What was verified on 27 October 2026

After correcting the media candidates, the in-app browser displayed **Audio connected** with its microphone off. A separately joined synthetic peer then sent a quiet generated tone: the browser received a remote audio element with `readyState=4`, `paused=false` and advancing playback time. The local synthetic two-peer check also passed audible raw routes in both directions and server mute/unmute, with no provider requests. This verifies the connection fix and receiver transport/playback mechanics; physical headphone audibility, human Chrome listening, device quality and real interpretation remain separate acceptance checks. Chrome automation was unavailable, so a completed native-Chrome listening test is not claimed.

The first output now waits for an RTC subscriber before synthesis or PCM delivery. This wait is bounded at five seconds; original audio has a bounded startup buffer, and timeout or overflow is reported instead of silently treating a missed phrase as a pass. Allow the initial track to connect, then review each spoken word in the listening test. This is a first-subscriber guarantee; simultaneous readiness of every member of a larger shared-language audience still needs its later multi-party acceptance check.

For an optional receiver-only check while a browser is already in a raw-audio room:

```powershell
.\server\.venv\Scripts\python.exe scripts/check_browser_audio.py --room YOUR_ROOM_CODE
```

Replace `YOUR_ROOM_CODE` with that room's invitation code. This joins a disposable local participant, sends a three-second generated tone, and leaves automatically. It does not open a microphone or use a speech API. It refuses a live/demo backend or a non-loopback API/media endpoint. Publishing the tone is not itself a listening pass: check browser playback and what you hear.

## Automated checks without speech-provider requests

Stop the interactive launcher first so its media ports are free:

```powershell
npm run test:web
.\server\.venv\Scripts\python.exe -m pytest server/tests -q
npm run build
npm run test:rtc
```

`test:rtc` owns and stops its own local LiveKit instance, with signaling on loopback. It runs two-peer raw forwarding, three-speaker/six-branch interpretation routing with provider doubles, and mixed same-language forwarding/mute/expiry checks. The generated tones are not human speech and the fixture translation is not model output. The raw check writes `work/local/transport-check.json`; its capture→received-PCM timing uses one process clock and includes setup/codec buffering. It is neither translation latency nor physical speaker playback delay.

## Repeat the local startup measurement

Keep `npm run dev:local` running so the local LiveKit server is available. In a second PowerShell terminal at the project root, run the following checks sequentially. Avoid running builds, test suites or heavy applications alongside a timing trial. The harness disables providers and isolates raw transport with screening off; it creates synthetic peers and does not open your microphone.

```powershell
.\server\.venv\Scripts\python.exe scripts/verify_transport.py --trace --output work/cold-start/recheck-01.json
.\server\.venv\Scripts\python.exe scripts/verify_transport.py --trace --output work/cold-start/recheck-02.json
.\server\.venv\Scripts\python.exe scripts/verify_transport.py --trace --output work/cold-start/recheck-03.json
```

Each trial connects two fresh peers, waits one second, then measures source capture to received non-silent PCM on one process clock. It also asserts routing, unpublish-on-mute, receiver detachment, no audio from a still-publishing muted source and recovery after unmute. `--trace` adds anonymous first-signal/publication/subscriber markers without retaining audio. Failed runs write a failed report and must remain in the record. Use new report names to preserve earlier evidence.

The 28 October fresh comparison had three runs and six directions in each group: median **686.500 → 210.535 ms**, about **69.3% lower**. The Performance page has the curated before/after record, every direction and an export. Recheck files do not automatically overwrite that record. Compare the same setup and boundary, include all outcomes and document changes in host load. The older 12,132.83 / 4,669.78 ms incident is shown separately and excluded from the fresh medians. These checks do not measure acoustic playback, translation or voice cloning.

After the isolated runs, check that local screening still forwards normally in monitoring mode:

```powershell
.\server\.venv\Scripts\python.exe scripts/verify_screening_transport.py --actual-model-monitor
```

This last test uses the installed free CPU model and generated signal, makes zero provider requests and is not a detector-accuracy test. Voice cloning remains deferred. For the next actual translation step, follow the separately approved workflow below.

## Move to two-person interpretation

The real speech key is already stored privately on this computer. Still required: the **Evon endpoint URL and exact served model**, plus its authentication if required. This can be an approved Gnani hosted endpoint or a compatible deployment. An ordinary Gnani STT/TTS key alone does not establish this MT service.

Configure the real services in `server/.env`, stop local transport and use the live reporting workspace (`npm run dev:checks`). Keep standard voices. Begin with a bounded typed sentence to check MT/TTS; then use microphone input to include STT. Each real provider test still requires its own explicit flow approval. The completed earlier speech round trip is not a grant for a meeting.

For each everyday sentence, review source transcription, translated meaning and audible target output separately. Preserve numbers, units, names, questions, negation and conditions. Clarify ambiguous words with the speaker. Compare Performance server stages with a separately described listener-delay measurement. Record failures as well as successes.

## Second device, then Sites

The local launcher is deliberately limited to this computer. On another device, `localhost` points to that device. For microphone access beyond loopback use a trusted HTTPS frontend/API and WSS media endpoint with reachable media ports; do not disable browser certificate validation. This follows [LiveKit's local connection guidance](https://docs.livekit.io/transport/self-hosting/local/) and [browser microphone requirements](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).

Before a second-device run, configure the reachable host, TLS/certificates, exact allowed frontend origin and LiveKit media networking. A simple HTTP tunnel for the webpage alone does not route WebRTC media. Choose and verify that setup when the first local listening gate passes.

For Sites, the frontend must use the reachable HTTPS API and LiveKit service. The Python agent/media server do not run inside the static Sites publication. The current static demo is therefore not a live second-device test. Keep Sites publication for the agreed hosted testing stage.

Zoho or another deployment comes later. Verify the actual selected service supports the server processes, SSH and UDP/media networking before purchasing or provisioning anything. The existing [deployment guide](../deploy/production/README.md) prepares a general Linux VM; it is not proof that a particular managed hosting plan provides those capabilities.
