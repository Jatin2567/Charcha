# Charcha operating state — 6 November 2026

Application: https://charcha-234398803946.asia-south2.run.app/

## Deployed reviewer update — 10 November 2026

The new [reviewer workflow](REVIEWER_GUIDE.md) adds expiring administrator-issued
reviewer invitations, session-private Gnani/Evon resource selection and explicit
prejoin preparation. The matching API/frontend release was deployed and checked
on 10 November: health, served controls, identity configuration and anonymous
access restrictions passed, and 13 deployed source-file hashes matched. No
invitation or authenticated live provider flow was part of that verification.
The dated operating observations below remain historical.

An authorized host can prepare interpretation on the Prejoin page for up to 15
minutes before connecting media. Account/access/room expiry can shorten that
window. Status reads never start or renew compute. Once actual media connects,
the normal occupied-meeting hold takes over. New translated microphone sources
wait for the ready response. Personal endpoints use their own provider account;
shared resources retain the application's controls. An externally managed VM must
be stopped by its owner; releasing a Charcha hold does not stop such a VM.
Personal providers still require running Charcha application, identity and
LiveKit media services; they do not bypass hosting or make a stopped app available.

## Meeting flow

### Refreshing a meeting — 9 November correction

The browser previously reused its saved 60-second LiveKit join credential after a page refresh. A valid meeting membership could therefore appear expired. The connection endpoint now authenticates that existing membership and issues a fresh short-lived media credential for the same participant. It does not extend the membership or bypass host admission, sign-out, explicit departure or room expiry. Voice enrollment stays attached to the same seat. Every new browser connection requests this credential; microphone and camera start off. This reconnect is not a new voice enrollment.

Local verification recorded 322 passing frontend tests and 60 focused backend tests on 9 November. Isolated Chrome reloaded a correctly signed expired cached media token and reconnected real local WebRTC with the same participant, microphone/camera off and no capture requests. Explicit departure cleared the seat; replay was denied. No providers were used. The `refresh-connection-20261109` release passed hosted health, served-bundle and backend hash checks. A reconnect still requires available network/media services; this is not uninterrupted audio during a page reload.

1. Sign in as `jatin.aggarwal1098@gmail.com` to create an interpreted meeting.
2. Share its invitation. Guests sign in, request entry, and the host admits or denies them.
3. Each speaker chooses their listening/speaking language, consents to personal-voice synthesis,
   and records 5–30 seconds of their own speech in the meeting's voice setup card. Listening
   does not require enrollment. The temporary embedding is reused for that meeting and removed
   when its membership expires or leaves. Deleting it mutes the speaker until setup is repeated.
4. When the first admitted participant connects meeting audio in an interpreted room, the server
   starts preparing Evon, even while that participant is muted or completing voice setup.
   The shared GPU stays warm through silence and between translations for the whole occupied
   meeting. The room shows elapsed startup from actual backend state. Once ready,
   Prisma STT → Evon translation → cloned Gnani synthesis sends each
   listener their chosen language. Same-language listeners hear original audio.
5. Open Performance in a second tab. Inspect measured server stages, transport/receiver samples,
   errors, sample counts and observation times. Missing measurements remain unavailable.
   Model translation time is not speech-end-to-listener latency.
   After leaving, the page opens the latest saved report; use Meeting report to select another
   call. Reports are linked to the signed-in identity, persist across a new login and server restart,
   and contain no transcript, audio or voice embedding. Connection snapshots and receiver checks
   are private to their own account. The last browser connection snapshot is labelled as saved.
   Reports are checkpointed every five seconds and finalized at departure/expiry; a restarted
   unfinished meeting is labelled interrupted. Retention is up to 90 days and 500 stored reports.
   Calls whose measurements were discarded before this feature cannot be reconstructed.

## Compute and billing

- Delhi hosts the app, identity, LiveKit and CPU VoiceShield. GPU inference is on Modal's Asia
  allocation; this is not a verified India-only data-residency deployment.
- `charcha-evon` uses the existing pinned Evon weights/cache, one A100 80 GB at most, zero minimum
  and buffer containers, and a 120-second idle scale-down setting. Startup and warm idle time
  consume compute credits. Scale-down timing is provider-controlled, not an exact stopwatch.
- Meeting occupancy is checked locally every five seconds against actual LiveKit connections and
  valid memberships. While at least one authorized interpreted meeting is occupied, one shared
  background task checks model health every 45 seconds to keep it warm. This consumes GPU time
  during silence as requested. Multiple meetings share the same GPU rather than spawning one each.
- Local engine status and Performance reads never call the GPU or extend a meeting. Waiting-room
  requests, unused invitations, original-audio rooms and expired memberships do not hold compute.
  Last explicit departure releases the hold at the next occupancy check; unexpected disconnects
  get a 30-second reconnect grace. Modal then applies its 120-second idle scale-down setting.
  A server crash stops renewals, so it cannot leave a permanent minimum GPU allocation behind.
- The owner requested manual Gnani billing monitoring. The app records attempted request/audio
  units, but does not calculate a current rupee balance or enforce a Gnani monetary ceiling.
  Existing historical records are retained. `charcha-admin` can change speech billing controls;
  setting the estimated budget to zero pauses new speech use. A nonzero estimated budget cannot
  correctly account for cloned voices until their rates are configured.
- At the read-only billing check: Modal $23.77 credits remaining, $6.23 used, $0 charges. The
  workspace usage limit is now $30, matching included monthly compute. GCP showed ₹27,777.69
  promotional credits remaining, expiring 22 January 2027. These are dated observations only.
- The former one-hour VM stop was extended to seven days to bound unattended GCP use under the
  existing ₹5,000 authorization: the current run stops around **13 November, 06:49 IST**. Extend
  only after reviewing actual remaining credits and applicable authorization. GCP's console also
  displayed an account-verification notice; the account owner must handle identity/payment checks.

## VoiceShield and accuracy

VoiceShield runs the pinned AASIST ONNX audio classifier on incoming microphone audio. It does
not classify transcript keywords, and it does not screen Charcha's own synthesized output as an
incoming attacker. No reference recording is needed to run this classifier. The separate voice
reference is for synthesis, not proof of identity or evidence that someone is human.

The model needs 4,037.5 ms of audio plus compute time. Scores are uncalibrated and Indian meeting
audio accuracy is unverified. It defaults to monitoring; a flag means review, not proof of fraud.
The host may switch monitoring off. Existing enforcement code is experimental and is not enabled
by default. Short/incomplete windows, silence or model failure must not become a human verdict.
A claim of immediate or universally accurate detection is not supported. Independently labelled
human and synthetic samples are still needed for a held-out accuracy evaluation.

## Verification and remaining acceptance

### Queue and measurement correction — 7 November 2026

- Live interpretation prepares at most two turns per speaker (current plus one lookahead), with
  bounded PCM buffers and ordered delivery. Preparation overlaps existing playback; it never
  mixes successive turns on the same audio route. `TRANSLATION_LOOKAHEAD` defaults to 2.
- `TRANSLATION_QUEUE_MAX_AGE_SECONDS` defaults to 4. Unstarted old turns, or prepared turns still
  waiting behind previous output beyond that deadline, are cancelled visibly with a repeat prompt.
  Their captions remain and cancelled samples do not enter successful latency percentiles.
  Already playing audio is not truncated. Longer translated speech still limits conversation pace.
- Server reports distinguish preparation queue, preparation-to-first-buffer, output wait, provider
  processing STT when available, and energy-estimated server-ingress speech-end intervals. A missing
  provider processing event remains unavailable; legacy total timings are explicitly partial.
- Automatic receiver observations correlate authenticated per-turn LiveKit markers with a quiet-to-
  energy transition in the listener's decoded audio. Browser clocks are calibrated against the API;
  samples include RTT/poll/frame uncertainty. Muted, blocked, late/overlapping, stale-clock and
  ambiguous-source observations stay unmeasured. No microphone uplink or physical speaker output
  is measured; this is not an acoustic speech-to-ear benchmark. A physical recording is still needed
  for that assertion. Keep the call tab visible to avoid browser timer throttling.
- Report snapshots are queued and coalesced, then written outside the audio event loop. Failed writes
  retry with bounded backoff; account-scoped status distinguishes pending, saved and retrying. Calls
  continue during storage failures. Shutdown attempts a bounded flush, but pending memory can still
  be lost during abrupt termination. The UI must never describe pending data as committed.
- Local verification uses fake providers, real local WebRTC peers, injected database failures and
  browser audio fixtures. These establish routing, ordering and timing behavior, not live provider
  speed or translation accuracy. No GPU/STT/TTS requests are needed for these checks.

Earlier validation records below refer to their original release:

- Full offline backend suite after the meeting-lifecycle correction: 1,425 passed, 1 skipped;
  frontend suite: 297 passed, including repeated unmute without new startup requests.
- Meeting-held lifecycle correction: 17 focused offline tests passed, covering silent meetings,
  shared concurrent meetings, last departure, reconnect grace, expiry, startup cancellation,
  and status/access requests that must not start a GPU. Provider health responses were mocked.
- Live release health, served frontend components and anonymous access restrictions verified.
- Actual hosted settings: personal voice required, no product participant cap, owner-monitored
  speech billing, local AASIST ready, screening mode `monitor`.
- One real Evon canary: 229,589.29 ms cold startup and 1,333.03 ms Hindi→Tamil text translation.
  No Gnani calls in that canary. Meaning was not independently reviewed. The record is saved in
  ignored `work/serverless-canary-20261106.json`; it is not inserted into live meeting metrics.
- After the canary, Modal listed no running containers while the hosted application remained
  available. The later billing snapshot showed $7.04456801 gross metered usage and $0 billed;
  compute charged to included credits was about $6.63, roughly $0.40 above the earlier snapshot.
  Billing reports may lag. This is verification of one idle shutdown, not a promise of free hosting.
- Needed from participants: consented voice enrollment and a real two-device listening test,
  followed by the language directions and multi-party load they intend to use. No measured
  cloned-speech quality, full acoustic latency or detector accuracy is claimed from unit tests.
- No product participant cap does not mean infinite capacity: this single server/GPU has finite
  bandwidth/CPU and provider concurrency. Overload surfaces as waiting/errors, never fake success.

Historical test-stage instructions elsewhere describe their original dates. This operating policy
and the owner's newer instructions supersede their per-flow approvals and deferred-cloning notes.
