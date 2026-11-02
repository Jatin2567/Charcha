# Standard-voice conferencing — first Modal stage

Updated 30 October 2026. The owner approved **at most $10 of Modal compute** for
Evon compatibility and Hindi↔Tamil testing. Screening is off and cloning is
deferred. Hindi, Tamil, Bengali, Telugu and Marathi are supported language
choices; that does not establish five-device or live-provider acceptance.

## Cloud checkpoint

The owner renewed the `artha-mesh` CLI login for workspace `jatin2567`.
Authenticated billing and App-list checks passed. Metered and billed cost were
zero and no App existed at that preflight. Sign-in is complete; it does not
establish GPU eligibility, model readiness or translation quality.

The dashboard usage ceiling has been lowered to **$10**. Its effective default
net-charge limit is **$0** while the observed credits cover that ceiling. The UI
disables saving an explicit zero when unchanged from that default. These are
observed settings, not a billing guarantee. The cache is verified and the A100
loaded Evon. After correcting the target-language prompt, both text directions
completed. The first approved speech flow completed Hindi→Tamil and stopped
at Tamil recognition. A separately approved fixed-clip Tamil→Hindi follow-up
then completed. Both reports are retained and both grants are closed; meaning
review and physical-device acceptance remain pending.

The exact App is stopped with zero active containers. The latest post-stop
snapshot reports **$1.63964278 metered/$0 billed**, subject to billing lag. Private
account evidence stays under `work/modal-stage-01/`; the preflight zero is not
the stage cost. See [MODAL_TESTING.md](MODAL_TESTING.md) for the actual partial
result and the fresh-session procedure.

The GCP project has no existing VM. Hosting remains conditional on real-device
needs after the first model/voice check. The $10 Modal allowance does not fund
GCP. The existing [production generator](../deploy/production/README.md) now
preserves Modal authentication and language-specific standard-voice overrides.

## Camera and local test

The implementation now has private prejoin preview, camera publication in the
existing LiveKit room, remote video tiles, late-join permissions and visible
device/permission errors. Camera capture begins only after a button click.
Joining, changing language or reconnecting media leaves the camera off.
Leaving stops hardware before waiting for signaling. Video elements are muted;
original microphones remain interpreter-only. Member tokens permit camera and
microphone without granting screen sharing.

Run from the repository root:

```powershell
node scripts/local.mjs --screening-off
```

This launches `http://127.0.0.1:5180` with self-hosted local LiveKit and transport
mode. Vendor credentials are cleared; this check cannot consume speech credits
and forwards original audio without translating it.

1. Open normal Chrome, select **New conversation**, and copy the invitation.
   Join with a test name and Hindi as the listening language.
2. Open the invitation in Incognito and join with another name and Tamil.
   Camera and microphone start off in each joined browser.
3. Select **Turn camera on** in one window and handle its permission yourself.
   Confirm video appears in the other tile. Turning it off must remove the remote
   picture. Repeat in reverse; test one publisher at a time if the shared physical
   camera is busy. **Preview camera** before joining is private and stops at join.
4. Wear headphones, unmute the intended speaker and check original audio in each
   direction. This is local capture/routing, not Hindi→Tamil translation.
5. Change language or reconnect media. Verify the camera returns to off, then
   explicitly enable it again. Leaving must stop the camera indicator.
6. Open **Performance** from the call. Connection diagnostics, receiver probes
   and translation timings have separate boundaries and exports. A local probe
   is synthetic transport evidence, not translated microphone-to-ear latency.

For two physical devices use prepared HTTPS or the deployed public HTTPS host;
another device's loopback address does not reach this laptop. Certificate trust
was previously deferred by the owner and has not been installed. See
[TWO_DEVICE_TESTING.md](TWO_DEVICE_TESTING.md).

## Evidence and limits

- The approved live stage verified the 13-shard cache and native A100 loading.
  Initial Hindi→Tamil text echoed its source; prompt v2 produced two text responses
  in 875.225 and 411.614 ms, with meaning review still pending. The controlled
  stock-voice flow completed Hindi→Tamil: STT 4,348.833 ms, MT 630.005 ms,
  target-TTS first PCM 478.525 ms, STT-start→first target PCM 5,457.414 ms.
  That chain includes connection setup and 2.4 seconds of real-time source upload;
  it is not speech-end or listener delay. Tamil source TTS produced 3.2 seconds of
  audio, but Tamil→Hindi returned no final STT transcript and stopped without
  retry. Recorded units were 19 reserved STT seconds/two connections, one MT/37
  characters, three TTS/132 characters and zero enrollments: **₹0.4989 reference**,
  actual billing unknown. The grant is closed, the App is confirmed stopped and
  there are no containers. Further paid tests need new approval. Performance →
  **Saved checks** contains the redacted partial report; semantic, physical-listener
  and five-device acceptance remain unverified.
- Isolated two-peer synthetic camera RTC **passed**: 34 decoded video frames from
  30 captures, 50 synthetic microphone frames with zero original-audio
  subscriptions, camera unpublish detached the receiver, and no cleanup failures.
  This verifies SDK/SFU routing, not physical camera or browser capture quality.
  Evidence: `work/local/two-peer-camera-20261030.json`.
- The corrected **sequential first-PCM fixture passed** in 40.738 seconds:
  six local peers, five recognizers, all 20 synthetic MT/TTS branches, 25 recipient
  routes (including a second Tamil listener and same-language forwarding), and
  camera delivery to five peers. Camera unsubscribe preserved the microphones;
  structured cleanup reported no failures. Evidence:
  `work/local/five-language-first-pcm-20261030.json`.
- Earlier stress failures remain preserved. A diagnostic located the attempted
  Bengali→Telugu failure before synthesis, at receiver readiness. The fixture
  kept completed Python PCM observers open, multiplying SDK audio-event fan-out;
  its thread dump showed FFI queue contention. Closing each bounded observer
  after its first decoded sound resolved the sequential run without extending
  deadlines or changing production routing. RTC subscriptions and permission-leak
  checks remain active. A late SDK publisher negotiation error after closure is
  retained in the matching stderr log; it is not hidden by the structured report.
- This verifies first decoded synthetic PCM, not sustained playback, simultaneous
  speaking, real-provider translation, physical hardware or audible quality.
  Synthetic timings must not populate live translation latency percentiles.
- Real five-person speech needs reviewed admission settings. Defaults admit
  three STT sessions, two operations and 16 queued operations. First-stage two-person
  tests keep them. Five active microphones need at least five approved STT slots
  and measured operation/queue capacity. Raising queues alone does not make
  translation fast; the prepared Evon instance serves at most two sequences.

## Live acceptance order

1. With renewed Modal access verified, execute the
   pinned cache/readiness sequence in [MODAL_TESTING.md](MODAL_TESTING.md).
   Stop the owned app on completion or failure.
2. Run the bounded Hindi↔Tamil text check. Keep GPU/model startup separate from
   warm translation time and retain failed/incomplete answers.
3. Review one concrete Gnani flow before using its separate speech credits.
   A controlled provider-chain test and an actual microphone/receiver test must
   carry different evidence labels. Close its bounded grant after testing.
4. Review meanings with Hindi/Tamil speakers, then test two physical devices.
   Listener latency uses one shared recording clock, not separate device clocks.
5. Expand to the five-language/20-direction worksheet and multi-user conference
   under approved concurrency/request limits. Preserve cold/warm trials, failures
   and unattempted routes. Screening and voice cloning remain deferred.
