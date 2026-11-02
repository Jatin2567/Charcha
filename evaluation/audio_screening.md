# Local audio screening: implementation and evidence

The runtime never sends audio to an API. It accepts 16-bit little-endian mono PCM
at 16 kHz, keeps only bounded audio in memory, and scores complete 64,600-sample
windows (4,037.5 ms). Upload evaluation is limited to 30 seconds. Incomplete tails
are disclosed; a low score on partial coverage cannot allow the complete clip.

The [public FLEURS human pilot](../docs/PUBLIC_HUMAN_SCREENING.md) provides a
separate, licence-based human-only evaluation path. It does not manufacture
personal consent or speaker identities and does not relax the mixed-class
manifest checks below. Its measured false alarms do not establish AI detection
accuracy; no shorter live window is enabled.

## Model provenance

- Original model: NAVER AASIST, ASVspoof2019 Logical Access pretrained weights.
- Reviewed ONNX export: [SpeechAntiSpoofingBenchmarks/AASIST](https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST).
- Revision: `16774d458d86d2a021ae31646c1bf66a5331b53e`.
- SHA-256: `130e536266b7c537f9a13029e1612a9f392fd1cc827783683b6d1c062a3db5e1`.
- File: 1,615,195 bytes; MIT licence (NAVER copyright retained beside the download).
- Model input: `wav`, float32 `[1,64600]`; output `logits`, float32 `[1,2]`.
- Class 0 is spoof, class 1 bona fide, matching [upstream evaluation](https://github.com/clovaai/aasist/blob/main/main.py).
- Local CPU ONNX Runtime only; one inference thread by default, with two selected
  by the local launcher after a laptop comparison. No PyTorch pickle or upstream
  executable code is downloaded or loaded.

The model is foreign-origin, although inference runs locally. It is not an
Indian-trained or India-validated detector. The export publisher reports much
worse cross-domain results than in-domain results; those results are not our
measurements. No Indian-language meeting accuracy has been established.

## Installation and zero-credit smoke test

From the repository root:

```powershell
uv sync --project server --extra dev --extra screening --frozen
server/.venv/Scripts/python.exe scripts/fetch_audio_screening_model.py
server/.venv/Scripts/python.exe scripts/verify_audio_screening.py
```

The download is explicit, free and checksum-pinned; only model data and its licence
are fetched. The app never downloads at startup. The generated manifest and model
are ignored under `server/models/aasist/`. The smoke test uses local generated
tones, silence, chirps and clipping, and writes `work/audio-screening-smoke.json`.
It checks execution and timing, not deepfake accuracy. Its accuracy is always null.

With the local LiveKit server already listening on port 7880, real RTC routing can
also be checked without a browser, microphone or paid API:

```powershell
server/.venv/Scripts/python.exe scripts/verify_screening_transport.py
server/.venv/Scripts/python.exe scripts/verify_screening_transport.py --actual-model-monitor
```

The first run uses explicitly controlled verdicts to verify full-window holding,
allow release, suspicious/unknown withholding and mute cleanup. The second runs
the installed classifier on an unlabelled generated tone while proving monitor
mode still relays audio immediately. Results are under `work/local/`. Neither
run establishes speech accuracy or acoustic speaker-to-listener latency. Under
concurrent CPU load, inference can be significantly slower than an isolated warm
smoke test; retain both observations rather than advertising the fastest value.

## Interpretation

DSP reports RMS, clipping, silence, zero crossings and autocorrelation pitch.
The jitter and shimmer fields are consecutive voiced-frame variation proxies,
not clinical cycle-level measurements. None of these features establishes liveness.

AASIST logits are converted to an **uncalibrated** spoof softmax score. Experimental
thresholds are 0.8 for suspicious and 0.2 for allow, with unknown between them.
These thresholds are engineering defaults, not calibrated operating points.
Silence, severe clipping, insufficient audio, missing/invalid models and inference
failures abstain. Multiple full windows report the maximum spoof score; this changes
false-alarm behavior with clip length and must be evaluated accordingly.

Monitor mode never blocks. Any explicitly selected enforcement experiment must
buffer the whole decision window and disclose at least 4.04 seconds of observation
plus computation delay. It must not claim subsecond detection. An allow verdict
means only that this experimental threshold was passed, not verified identity,
consent or authenticity. Unknown is not a synthetic-voice accusation.

## Evaluation with consented recordings

Before scoring a real dataset, run an offline evidence check. It loads WAV data
but does not load the classifier, make network requests or infer labels:

```powershell
server/.venv/Scripts/python.exe evaluation/audio_screening.py --manifest evaluation/my-recordings.jsonl --validate-only
```

Each row additionally needs `consent: true`, a private `label_evidence` note,
`split: "calibration"` or `"evaluation"`, and anonymous `speaker_group` and
`source_group` identifiers. The source group identifies a recording source or
generator family, not a filename; all variants derived from it stay in one split.
Keep each speaker in one split too, including the reference voice for generated
speech. For example, use `speaker-03` and `generator-family-b` rather than names.
Keep actual consent and lawful-source records privately. Setting these fields
does not independently establish consent or label truth.

The preflight checks unique IDs, declared evidence, readable supported WAVs,
the minimum detector window, byte-identical decoded audio and speaker/source
overlap between splits. It also requires both labels in the held-out evaluation
split. It cannot find every near-duplicate, verify human labels or establish a
representative sample size. The exported preflight includes row numbers and
issue codes, not paths, speaker identities, source names, notes or audio hashes.
Exit code 2 means fix the dataset first. The example manifest is intentionally
incomplete and must not pass as real evidence.

Then require these checks before any CPU inference:

```powershell
server/.venv/Scripts/python.exe evaluation/audio_screening.py --manifest evaluation/my-recordings.jsonl --strict-manifest
```

Reports retain `by_split` summaries. Use **evaluation** results for held-out
claims; the printed headline selects that split when present. The combined
overall summary also includes calibration data and is explicitly labelled pooled. Never tune
thresholds using the held-out recordings. Existing manifests can still use the
legacy scoring command below, but its results have no dataset-preflight evidence.
Always include `classification_coverage_all_labelled` and `labelled_errors`:
the legacy `coverage` / `coverage_of_successfully_analyzed` metric excludes
unreadable or failed recordings, while the all-labelled denominator includes them.

Copy `audio_screening.example.jsonl` and supply local files with independently
known labels. The example references are placeholders, not a downloaded dataset.
Use ordinary speech about directions, schedules, food or greetings. Keep speakers
and synthesis sources separate between threshold tuning and held-out testing;
include Hindi, Tamil, other intended languages, noise, Opus/WebRTC, replay and
unseen synthesis systems. Record the lawful source/consent in a private dataset log.
Do not generate paid TTS samples without an approved bounded flow.

```powershell
server/.venv/Scripts/python.exe evaluation/audio_screening.py --manifest evaluation/my-recordings.jsonl
```

The report exposes false alarms, missed spoofs, unknown counts and classification
coverage overall, per language and per condition. Unknowns, fixtures and unlabelled
files do not become correct predictions. Accuracy on classified recordings must
always be reported with coverage; a six-clip smoke set is not a representative
validation benchmark. Recorded WAV audio is read locally and never copied into
reports. Reports contain diagnostics and supplied metadata only.
