# Five-language conference calls

Hindi, Tamil, Bengali, Telugu and Marathi use the same room, microphone and
camera controls, language routing, captions and standard-voice synthesis.
Five languages give 20 directed pairs. The October 31 batch permits ten
pairwise calls. Every language serves twice as a source and twice as a target.
An automatic delivery result applies only to its recorded direction.

## Operator run

Run the following from the repository root. The first command describes the
stage. The second starts an isolated loopback media server and sends a saved
public clip through two real RTC peers using local provider doubles.

```powershell
.\server\.venv\Scripts\python.exe scripts/run_five_language_calls.py
.\server\.venv\Scripts\python.exe scripts/run_five_language_calls.py --rehearse
```

Execution with the reviewed plan hash is single-use. The operator runner
reserves an exclusive stage directory, checks the previous deployment and
workspace meter, starts one private cached A100 with an absolute expiry, and
stops it in cleanup. It opens and closes one grant per route in the regular
live usage ledger. Each grant allows one STT connection of up to 25 seconds,
one MT call of up to 500 source characters, and one standard TTS call of up to
300 characters. Failure keeps the reservation. Two consecutive route failures
end the batch. The maximum Gnani reference under these caps is ₹9.975 for
ten attempts. Compute reservations, metered snapshots and invoices differ.

The recorded source enters as a microphone track. The receiving client checks
the agent identity, original speaker and requested language, then observes
decoded non-silent audio. Private results retain the source reference,
recognized and translated text, and decoded target WAV for listening. The
public report exports only allowlisted metrics after the grants and deployment
have closed. Source WER uses normalized words from the first final segment
against the entire reference. Review the texts to distinguish early
segmentation, alternate spellings and lost meaning. Capture-start timing
includes source playback. Physical speaker output requires a separate shared
recording clock.

Audio is from Google FLEURS, Conneau et al. (2022), CC BY 4.0. The saved
evaluation copies are converted from float32 to mono 16 kHz PCM16. Source
IDs, hashes and attribution are in the local FLEURS collection. See the
[collection record](PUBLIC_HUMAN_SCREENING.md).

## Two people

1. Complete **Test lab → Two-device audio** in original-audio mode. Windows
   certificate trust on the second device was deferred. Follow the
   [trusted-LAN setup](TWO_DEVICE_TESTING.md) before trying a LAN invitation.
2. In **Test lab → Five-language calls**, select a direction. Open a real
   conference with the corresponding two language choices. Use separate
   headphones, join muted and enable each microphone deliberately.
3. With a fresh live-call allowance, speak the displayed phrase once. Ask
   the listener to repeat its meaning before showing the captions. Record
   the answer and whether the detail, number and correction survived.
4. Save a separate outcome for each direction and export it before moving to
   another browser. For a subsequent group trial see **Test lab → Group calls**.
   Five simultaneous live speakers require a separate concurrency review.

These calls use standard voices with screening off. The ten-flow approval
belongs to the recorded batch only.

## Recorded outcome

Nine of ten planned routes reached the receiving RTC peer. All five source
languages and all five listening languages delivered at least once. Bengali
to Marathi encountered a local setup permission error before any speech
provider use. That route subsequently passed a provider-free RTC rehearsal.
Ten grants closed, covering nine STT connections, nine MT calls and nine TTS
requests. The ledger reserved 106 STT seconds and 867 TTS characters for a
₹3.1359 reference. The Modal workspace meter changed by about $0.60 and
showed $0 billed at shutdown.

Across the nine deliveries, median server first PCM was 1.56 seconds and
median capture start to the receiver’s first non-silent PCM was 12.70 seconds.
Source clips last about 8–11 seconds. Physical mouth-to-ear latency is
unmeasured. Both recognized versions of the Marathi source contained 1972
where the reference contained 1976. The translations repeated this error.
The public report flags it separately from successful delivery.

Open `work/five-language-conference-20261031/listen.html` to play the two
ends of each successful call locally. The private audio stays out of the site
bundle.

During a live call, open **Settings → Audio playback** to view the microphone
and incoming audio waveforms or lower incoming voices while you speak. Both
controls work on the listening device. The microphone still requires explicit
unmute. The local receiver test tone keeps its normal volume.

In **Audio lab**, choose a mono 16 kHz PCM WAV and click **Compare with an
8 kHz phone line**. Play the original or a band-limited version with optional
background hiss. The browser creates both previews locally. This listening
exercise does not measure provider recognition on degraded speech.

## Simultaneous group transport

The single-process local stress harness timed out when five publishers and
six RTC clients shared one Python event loop. With six isolated peer processes,
the five publishers overlapped for three seconds. The server created all 20
synthetic translation branches. Receivers decoded all 25 expected audio routes,
including a sixth participant sharing Tamil and same-language forwarding.
No peer reported an unexpected subscription. The SDK emitted late teardown
warnings. This measures simultaneous transport with provider doubles. Sustained
five-way live inference and physical listening still require separate trials.

```powershell
.\server\.venv\Scripts\python.exe scripts/verify_group_conference.py --output work/local/new-group-report.json
```
