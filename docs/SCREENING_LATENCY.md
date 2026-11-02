# Local screening latency experiment — 29 October 2026

The local launcher now selects two ONNX CPU threads after a matched local comparison. The deployed-service default stays one thread so another host is not silently tuned using this laptop's result. The model checksum, 64,600-sample input, experimental allow/suspicious thresholds and full-window release gate are unchanged. No API, new model download, paid server or voice cloning was used.

The later [public human-speech pilot](PUBLIC_HUMAN_SCREENING.md) measured 14 false
alarms and 12 unknowns in 50 genuine clips. It shows why the timing improvement
below does not certify detector accuracy or justify shortening the live input.

## What improved

The installed AASIST ONNX export consumes **64,600 mono samples at 16 kHz: 4,037.5 ms**. That collection duration is distinct from CPU processing, queueing, recognizer readiness and listener output. Current enforcement waits for classification before dispatching source audio to recognition or forwarding.

Four deterministic synthetic signals were reused byte-for-byte across one, two and four CPU threads. Each setting has 20 warm full-analysis observations: four fixtures × five repeats. A second experiment used two simultaneous callers, with 12 full analyses and six pair-completion observations per setting.

| Setting | Isolated analysis median | Two in-flight analyses median | Pair completion median |
| --- | ---: | ---: | ---: |
| One CPU thread | 403.500 ms | 810.884 ms | 821.249 ms |
| Two CPU threads | 268.460 ms | 524.416 ms | 529.804 ms |
| Four CPU threads | 317.499 ms | Not measured | Not measured |

Two threads saved about **135.040 ms / 33.5% of isolated analysis time** in this experiment. Adding the unchanged input duration gives an arithmetic estimate of **4,441.000 → 4,305.960 ms**, about **3.04% lower**. This is not a measured microphone-to-listener or STT→MT→TTS result. Queueing and up to one second of recognizer-readiness wait in the current enforcement path are outside this arithmetic estimate.

All compared diagnostic verdicts matched. Maximum raw-logit difference was `4.768371582e-7`, and maximum spoof-score difference was `3.926228676e-9`, within the predeclared `1e-5` / `1e-6` tolerances. The fixtures were all strongly suspicious (roughly 0.990–1.000); they provide no evidence about genuine speech, unseen generators, noisy Indian speech or near-threshold decisions. **Numerical parity is not proof of preserved representative accuracy.** Repeats are timing observations, not independent speakers or detection trials. Small sequential samples, filesystem caches and host load limit generalization.

Raw evidence: `work/screening-latency/compute-20261029.json` and `compute-concurrent-20261029.json`. The scripts also retain model/session initialization and first-call timings separately; those are not independently repeated device cold starts. Performance and Audio lab show the saved summary and export it without running a model or opening a microphone.

## Why the four-second window was retained

The separate [duration experiment](SCREENING_DURATION_EXPERIMENT.md) compared 0.5, 1, 2 and 3-second prefixes with the complete window. Short prefixes were repeated to fit the existing tensor shape only inside that offline experiment. Across five synthetic sources, all 25 windows scored; none of the 20 short-prefix flags changed, but the maximum score difference was **0.134706**. Repetition creates no additional observed evidence, and unchanged flags on these signals do not measure false alarms or missed deepfakes.

No shorter-input setting can release live audio. Inputs shorter than 64,600 samples remain unknown in the live screener. No prior allow verdict certifies future audio. Jitter and shimmer remain signal diagnostics, not an alternative early human verdict.

The 40-slot five-language manifest still lacks actual consented, independently labelled recordings and split groups; strict preflight blocks scoring and accuracy remains null. To evaluate a shorter model/window, use the same held-out recordings for paired full/short comparisons, with genuine, generated, replay, noisy and codec conditions. Report false alarms, misses, unknowns and failures per language as well as pooled results. Keep calibration speakers and generator/source groups separate from evaluation, lock thresholds before evaluation and declare acceptable regression margins and uncertainty before claiming accuracy preservation. The placeholder count is not a sufficient accuracy sample.

## Further ways to reduce delay

- **Monitor mode:** screening adds no hold to original audio, but a warning comes after the evidence window. Audio can already have been heard. This is an exposure policy, not an equivalent early blocking detector.
- **Overlap detection with recognition/translation:** a future design could prepare output in parallel and release it only after all corresponding source windows allow. It would send unassessed audio to speech providers and require exact window/utterance association, output withholding, cancellation and per-flow cost controls. It is not enabled by this work and has not been represented as an accuracy or E2E improvement.
- **A detector trained for short utterances:** evaluate a separately reviewed model and thresholds on held-out speech. The AASIST2 paper demonstrates why architecture/training changes are needed; it does not validate shortened inputs for this checkpoint.

References: [upstream AASIST padding](https://github.com/clovaai/aasist/blob/main/data_utils.py), [AASIST2 short-utterance paper](https://arxiv.org/abs/2309.08279), [ONNX CPU threading](https://onnxruntime.ai/docs/performance/tune-performance/threading.html).

## Reproduce without provider credits

From the repository root, use distinct output filenames to preserve prior runs:

```powershell
.\server\.venv\Scripts\python.exe scripts/benchmark_screening_compute.py --help
.\server\.venv\Scripts\python.exe scripts/compare_screening_durations.py --plan
.\server\.venv\Scripts\python.exe scripts/compare_screening_durations.py --diagnostics --output work/screening-latency/new-duration-diagnostics.json
node scripts/local.mjs --screening-enforce
```

The last command starts only the self-hosted local stack, clears provider credentials and selects two CPU threads. In a separate terminal, the local routing checks can run against its LiveKit server:

```powershell
.\server\.venv\Scripts\python.exe scripts/verify_screening_transport.py --cpu-threads 2 --output work/screening-latency/new-rtc-enforce.json
.\server\.venv\Scripts\python.exe scripts/verify_screening_transport.py --cpu-threads 2 --actual-model-monitor --output work/screening-latency/new-rtc-monitor.json
```

Enforcement routing uses controlled verdicts and checks the complete window plus verdict-before-audio ordering. Monitor exercises the actual CPU model with synthetic audio and checks that original audio is not withheld. Neither measures real-speech detection quality. Use Ctrl+C to stop the owned local stack. The CPU setting can be overridden using `AUDIO_SCREENING_CPU_THREADS` (1–4); repeat measurements before choosing it for another machine.
