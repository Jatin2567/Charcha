# Local screening duration experiment

The current live detector still requires **64,600 real samples at 16 kHz: 4,037.5 ms**. `scripts/compare_screening_durations.py` is a separate local laboratory tool. It cannot select a live policy or release/block meeting audio. No provider, microphone, model download, voice cloning or cloud resource is used.

## What the experiment changes

For each source recording, the tool first scores its first complete native window. It then compares prefixes of **0.5, 1, 2 and 3 seconds** from that same source with the native result. Each prefix is tile-repeated and truncated to the fixed 64,600-sample input tensor. Both the actual observed prefix duration and the model tensor duration are recorded; repeated samples are not counted as newly observed evidence.

This follows the shape of [upstream AASIST's evaluation padding](https://github.com/clovaai/aasist/blob/main/data_utils.py), which crops long clips and repeats short ones. That preprocessing capability does not establish that a short prefix retains the same information or accuracy as four seconds of speech. [The AASIST2 paper](https://arxiv.org/abs/2309.08279) reports that short utterances can degrade spoof-detection performance and evaluates architectural and training changes for that problem. It is not validation of shorter input for our current checkpoint.

The live `LocalAudioScreener` is unchanged: short audio still returns unknown instead of repeated-input confidence. The fixed-window enforcement gate is also unchanged.

## Commands

From the repository root in PowerShell, print or save the plan without loading a model, reading provider environment variables or generating audio:

```powershell
.\server\.venv\Scripts\python.exe scripts/compare_screening_durations.py --plan --output work/screening-latency/duration-plan.json
```

Choose a fresh output filename; reports are never overwritten. With the already-installed checksum-pinned CPU model, explicitly run bounded synthetic diagnostics:

```powershell
.\server\.venv\Scripts\python.exe scripts/compare_screening_durations.py --diagnostics --output work/screening-latency/duration-diagnostics.json
```

Five deterministic synthetic signals produce at most **25 analysis calls**, including five native baselines and twenty shorter comparisons. Synthetic fixtures have no genuine/spoof labels; report accuracy remains null and `accuracy_preservation_proven` stays false. These signals are execution/sensitivity diagnostics, not recordings of human or cloned voices.

The report counts analyzer calls and successfully scored model windows separately. The analyzer does not expose failed native inference attempts, so that separate attempt count is unknown during execution. Unknown results and errors are retained instead of being treated as agreements.

## Observed local diagnostic result — 29 October 2026

The installed CPU model scored all **25 model windows**. All five synthetic signals and their tiled prefixes remained above the experimental suspicious threshold, so **0 of 20 shorter-prefix verdicts changed**. The largest score change was **+0.134706** for the one-second amplitude-modulated prefix compared with its native full window. The native score for that signal was 0.859188, compared with 0.993894 for the repeated one-second prefix.

That score change demonstrates that shortening the evidence can change the model's response. The unchanged verdicts on these particular synthetic signals do not establish unchanged speech accuracy, false-alarm rates or miss rates. These scores are uncalibrated model outputs, not probabilities of fraud.

Evidence is saved in `work/screening-latency/duration-diagnostics.json`. No audio files, paths to private recordings, credentials or conversation transcripts are exported.

## Real speech evaluation remains blocked

An optional strict manifest mode reuses the existing consent, provenance, speaker/source split, duplicate-audio and WAV checks before model loading:

```powershell
.\server\.venv\Scripts\python.exe scripts/compare_screening_durations.py --manifest evaluation/five_language_screening.example.jsonl --output work/screening-latency/duration-preflight.json
```

The checked-in template is intentionally incomplete. This command currently reports **blocked_dataset**, zero analysis/inference calls and accuracy null. It must not treat pytest-generated WAV files or synthetic fixtures as independently labelled speech. A duration batch is bounded to five source recordings; larger manifests require explicit batch selection rather than silently taking the first five.

For a larger **fully validated** collection, use `--batch-index 0`, then 1 and so on, with a fresh report name for each batch. Every batch validates the entire original manifest before selecting up to five recordings, so cross-batch duplicate audio and speaker/source leakage are still checked. Recording indexes stay unique across the study. For the 60-source pilot, there are 12 batches, indexed 0–11. Keep the same reviewed manifest and frozen settings for all batches, retain failures and aggregate only evaluation rows; a batch agreement rate is not an accuracy result.

For an actually validated small manifest, each duration gets one observation per source recording. Calibration rows are excluded from held-out summaries; evaluation metrics report all source counts, classified coverage, false alarms, misses, unknowns and failures, including per-language counts. Declared metadata checks cannot independently verify consent or labels. A five-recording batch is exploratory and cannot establish non-inferiority, even if every verdict matches.

Before considering a shorter live window, freeze a duration-specific policy and thresholds using calibration data, declare acceptable false-alarm/miss changes and confidence requirements, then evaluate separate genuine, generated and replay recordings across the intended languages, microphones, codecs and noise. Never tune the candidate from the held-out results or pool the repeated prefixes as independent people/recordings. Current evidence does not support reducing the live evidence window.

## What can reduce delay while retaining the native evidence

- CPU/runtime optimization and model warm-up can reduce computation after the same complete input, with numerical score/verdict parity checks. This experiment does not select or activate a faster runtime.
- Overlapping downstream translation work with classification can reduce total pipeline waiting while still gating playback on the full verdict, but changes privacy/cost boundaries and needs separate release-order tests. It does not remove the native first-verdict evidence floor.
- Monitor mode avoids holding audio, while the screening result arrives later. This allows exposure before a verdict and must not be presented as equivalent to enforced blocking.

The current production policy remains unchanged. All experimental duration outputs have `live_activation: false`; voice cloning stays deferred.
