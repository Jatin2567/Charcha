# Five-language screening after the latency baseline

The [29 October latency study](SCREENING_LATENCY.md) records a CPU-only timing improvement and a separate [short-prefix experiment](SCREENING_DURATION_EXPERIMENT.md). Neither supplies labelled five-language speech accuracy. The full-window live gate is retained; shortening it remains blocked on representative evaluation.

Status: a [50-clip public human pilot](PUBLIC_HUMAN_SCREENING.md) now supplies
five-language false-alarm, unknown and CPU-time observations. Mixed-class
deepfake accuracy and live-provider latency remain unverified. The matched
human/AI collection protocol below still has empty recording slots.
Hindi (`hi`), Tamil (`ta`), Bengali (`bn`), Telugu (`te`) and Marathi (`mr`) are
the planned languages. This stage uses the already installed local CPU detector;
it needs no GPU, API call, voice cloning or paid server.

## Order of work

1. Complete the standard-voice, screening-off speech latency baseline in
   [FIVE_LANGUAGE_TESTING.md](FIVE_LANGUAGE_TESTING.md). Keep failed or missing
   routes visible; a simulated transport run does not complete that baseline.
2. Collect and validate the consented screening corpus below. Preparation and
   validation can happen now, but do not mix detector delays into the baseline.
3. Freeze the model, thresholds and dataset split, then score held-out recordings
   locally. Report detection errors separately from speech interpretation errors.
4. Repeat local audio routing in monitor mode, then explicitly selected enforcement
   experiments. Only combine screening with live translation under a separately
   approved provider flow; the offline commands below never authorize one.

The current GCP ceiling is ₹5,000 total: at most ₹2,500 for the latency phase,
with ₹2,500 reserved for later work. That ceiling is not an allowance to launch
extra services. This protocol spends ₹0 in provider credits. Standard-TTS recordings
already obtained during an approved latency run can be reused only with consent
and provenance; do not request additional samples from a paid generator here.
Voice cloning remains a later phase.

## Corpus template and honest labels

The [public human-speech pilot](PUBLIC_HUMAN_SCREENING.md) now provides an
immediate human-only false-alarm baseline without personal recordings. It keeps
synthetic detection metrics unknown and does not replace the mixed-class study.

Start new collection with the [60-source real-speech kit](REAL_SPEECH_TEST_KIT.md).
It supplies exact filenames, distinct preparation/evaluation scripts in all five
languages, a checklist and a bounded whole-pilot runner. The folders are already
prepared under `work/speech-screening-kit/`. Use that kit for the current clean
human-versus-standard-AI pilot; add channel and replay challenges afterwards.

The older channel-challenge template below remains an alternative protocol, not
an additional 40 recordings required for the current 60-source collection.

`evaluation/five_language_screening.example.jsonl` contains **40 missing-recording
placeholders**, eight per language. Every row deliberately has `consent: false`,
empty label evidence and empty speaker/source groups. Its labels describe the
intended collection slots, not established ground truth. Validation must fail
until actual files and independent evidence replace them.

| Split | Slots per language | Purpose |
| --- | ---: | --- |
| Calibration | 1 genuine clean, 1 generated clean | Exercise the preparation path; insufficient to calibrate thresholds reliably |
| Evaluation: genuine | 1 clean, 1 with background noise, 1 after Opus encode/decode | Inspect false alarms and abstentions across channel conditions |
| Evaluation: spoof | 1 generated clean, 1 generated after Opus encode/decode, 1 loudspeaker replay with noise | Inspect misses and abstentions across the selected attack conditions |

There are 10 calibration slots and 30 held-out evaluation slots. Three examples
per class per language are a **smoke test**, not an accuracy benchmark. A noise or
codec variant of a recording is not another independent speaker or source.
Report both clip counts and distinct group counts. Add a larger representative,
independently labelled corpus before choosing operating thresholds or making
Indian-language, unseen-generator or deployment accuracy claims.

Use normal conversation: meeting times, directions, classroom objects, numbers,
negation and corrected plans. Obtain clear participation/recording permission.
For genuine speech, an observer records a live speaker reading or saying the
agreed text, without synthesis or playback. For generated speech, retain a local
generation receipt identifying the generator/model/version and source file.
For replay, retain the known source, playback/recording device and room-condition
log. A model verdict, file name or suspected-sounding voice is never label evidence.

Human speech played through a loudspeaker is labelled a replay attack only under
this explicitly declared test policy; it is not an AI-generated voice. Keep its
condition separate. AASIST is not established here as a reliable replay detector.
For a replay based on synthesized audio, record both facts in the provenance log.
If the origin is uncertain, exclude it from the labelled accuracy corpus and
keep it separately as unlabelled diagnostic material.

## Collection and split rules

- Keep raw recordings and private consent/provenance logs under ignored
  `work/five-language/` or another controlled local folder. Do not commit personal
  audio, names, consent documents or identifying evidence to the public template.
- Create mono, signed 16-bit PCM WAV at 16 kHz. Each file must contain at least
  64,600 samples (4.0375 seconds), with useful speech, and be no longer than
  30 seconds. Record natural utterances rather than padding silence to meet the
  minimum. Preserve raw originals and document resampling, gains and edits.
- Record real noise/playback conditions, or document any offline augmentation
  including noise source, level/SNR and clipping. For an Opus condition, retain
  encode/decode settings (bitrate, sample rate and loss setting); the final WAV
  is decoded audio. Do not call a local codec round trip a real network test.
- Assign stable anonymous `speaker_group` and `source_group` values from actual
  provenance. Every derivative of one source utterance keeps the same source
  group. The same human speaker, synthetic voice identity, source recording or
  variant family must stay in one split, including across languages.
- Calibration and evaluation speaker/source groups must be disjoint. If making
  an unseen-generator claim, entire generator/model families must also be held
  out, not merely new utterances from a familiar model. The current validator
  checks declared speaker/source IDs; it cannot verify generator-family isolation.
- Reserve evaluation data before looking at scores. Keep the default experimental
  thresholds (allow ≤0.2; suspicious ≥0.8) frozen for this smoke run. If later
  tuning is justified, use calibration data only and record the new version.
- Record permission and independently known origin before setting `consent: true`
  and filling `label_evidence` with a local log reference. Anonymous groups must
  describe real membership; assigning a new group to every variant hides leakage.

Already generated standard-TTS outputs test a **known generator** only. They do
not demonstrate unseen-generator generalization or human-speaker performance.
No cloned voice or third-party paid synthesis is required by this protocol.

## Zero-credit commands

Run from the repository root. This first command intentionally exits with code 2
because the template lacks recordings and consent. It loads no model and performs
no inference, recording or provider request:

```powershell
server/.venv/Scripts/python.exe evaluation/audio_screening.py --manifest evaluation/five_language_screening.example.jsonl --validate-only --output-dir work/five-language/screening-preflight
```

The report is `work/five-language/screening-preflight/dataset-preflight.json`.
Expect `ready_for_scoring: false`, `accuracy: null`, `provider_calls: 0` and
`inference_calls: 0`. Planned split counts are not evidence that recordings exist.

When recordings are available, copy the template to
`work/five-language/screening.manifest.jsonl`. Put the WAV files in the adjacent
`recordings/` folder so the relative paths resolve there, then replace every
placeholder using the rules above. Do not overwrite an existing populated
manifest. Validate the copy first:

```powershell
server/.venv/Scripts/python.exe evaluation/audio_screening.py --manifest work/five-language/screening.manifest.jsonl --validate-only --output-dir work/five-language/screening-dataset
```

After the latency baseline and dataset review, the local-only scoring command is:

```powershell
server/.venv/Scripts/python.exe evaluation/audio_screening.py --manifest work/five-language/screening.manifest.jsonl --strict-manifest --output-dir work/five-language/screening-results
```

Strict mode stops before model construction if evidence/format checks fail. A
passing preflight checks declarations, WAV format, exact decoded-audio duplicates
and declared group separation. It cannot authenticate consent, labels, near
duplicates, languages, representativeness or statistical independence. Independently
review those before interpreting a score. Retain the manifest and report version.

## Required screening report

Use `results.jsonl` for individual outcomes and `summary.json` for aggregates.
Report **evaluation-only** results per language and condition. The evaluator's
pooled `overall`, `by_language` and `by_condition` summaries include calibration;
do not present those as held-out performance. Use `headline` for the held-out
total and filter rows to `split == evaluation` before language/condition analysis.

For each language, include the following, with denominators and counts:

| Measurement | Meaning |
| --- | --- |
| Genuine allowed / false alarms | Genuine clips allowed / incorrectly flagged suspicious |
| Spoof flagged / missed | Spoof clips flagged suspicious / incorrectly allowed |
| Unknown genuine / unknown spoof | Abstentions, counted separately and never as correct |
| Failed recordings | Input or execution failures, not detector decisions |
| Classification coverage | Classified clips divided by all labelled evaluation clips, including unknowns and failures in the denominator |
| Conditional false-alarm and miss rates | Errors divided by classified genuine or classified spoof clips respectively; show unknowns alongside them |
| Compute p50 / p95 | Detector computation only, including sample count and CPU/model version |

Do not call `1 - miss rate` whole-system protection: unknown/failed clips are
excluded from that conditional rate and monitor mode does not block anything.
No observed errors in a handful of clips proves neither safety nor high accuracy.
Label score thresholds experimental; the spoof softmax score is uncalibrated and
is not a probability of authenticity. DSP jitter/shimmer remain diagnostics.

## Separate detector delay from conversation delay

The installed AASIST model requires **64,600 samples at 16 kHz = 4,037.5 ms** per
window. Cold model start, CPU load, queueing and computation add time. Local
inference alone is not speech-to-listener latency and cannot establish a
sub-150-ms deepfake decision from a fresh utterance.

| Mode | What to measure | Expected routing behavior |
| --- | --- | --- |
| Off | Original baseline STT/MT/TTS and listener timing | No detector hold |
| Monitor | `audio_window_ms`, `queue_ms`, `compute_ms`, time to verdict, and audio arrival relative to baseline | Audio continues before a full-window verdict; synthetic speech can already reach listeners |
| Enforce | Those fields plus `hold_ms`, first permitted audio, withheld/overload/partial-window counts | Complete window is assessed before allow release; suspicious, unknown and incomplete/overloaded windows are withheld |

`hold_ms` is currently an **estimate of window duration plus screening elapsed**,
not an acoustic stopwatch measurement. Queue time includes scheduling overhead.
Use the exact decoded sample count and verdict-before-release ordering to verify
enforcement; startup decoder silence can precede a later source-tone timer.
Measure audible listener latency separately on the two-device setup, after its
HTTPS trust setup is completed. Do not add unrelated percentile values to invent
an end-to-end percentile. Pair monitor/enforce runs with comparable off runs and
record model cold/warm state, device/CPU load and the complete timing boundary.

Existing `scripts/verify_screening_transport.py` tests controlled verdict routing;
`--actual-model-monitor` exercises the installed model on an unlabelled generated
signal. Those zero-credit transport checks are useful implementation evidence,
but neither is the real-speech five-language detection test described here.

## Completion gate

This phase is complete only when the language latency baseline is recorded,
real consented files pass independent review and strict preflight, evaluation-only
results exist for all five languages, monitor/enforce routing evidence is retained,
and unknowns/errors plus timing boundaries are visible in the report. Until then,
show it as prepared or pending, with no fabricated score or claimed success.
