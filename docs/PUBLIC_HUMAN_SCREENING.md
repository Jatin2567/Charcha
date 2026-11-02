# Public human-speech screening pilot

Prepared 29 October 2026. This replaces the need to personally record the human
half of the initial detector evaluation. It does not complete the synthetic
speech, live microphone, translation or two-device tests. No API credits, paid
GPU, model training or voice cloning are used by the commands below.

## Source and collection

Source: [Google FLEURS](https://huggingface.co/datasets/google/fleurs),
Conneau et al. (2022), *FLEURS: Few-shot Learning Evaluation of Universal
Representations of Speech*. Published licence:
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Pinned revision: `70bb2e84b976b7e960aa89f1c648e09c59f894dd`.

The selected configurations are Hindi `hi_in`, Tamil `ta_in`, Bengali `bn_in`,
Telugu `te_in` and Marathi `mr_in`, all from the publisher's `test` split. These
are publisher-described human readings, selected deterministically in archive
order after duration and duplicate checks. Public reuse permission and the
publisher's human-source description are the provenance basis; personal
recording consent and identities have not been independently reverified here.

The sample contains ten original recordings per language, **50 total**, each
8–20 seconds long with a distinct sentence within that language. The originals
are mono 16 kHz IEEE float32 WAVs. Local analysis copies quantize them to signed
16-bit PCM with sample counts preserved; no resampling, gain, denoising,
trimming, synthesis or repeated speech is applied to the stored source copies.
Original/analysis SHA256 hashes, revision, filenames and attribution remain in
the private local manifest. The source supplies no speaker IDs. Distinct
speaker count, speaker independence and overlap with detector training remain
unknown; clip counts must not be presented as counts of independent people.

The completed collection is under `work/public-human-fleurs-20261029-v2/`:

```text
originals/                    # Untouched publisher WAVs
recordings/                   # PCM16 analysis copies
metadata/                     # Original per-language test.tsv
manifest.public-human.jsonl   # Exact source IDs, transformations and hashes
collection-report.json
ATTRIBUTION.txt
screening-study-01.json        # Local detector study, when completed
```

Raw audio and source metadata remain in ignored `work/`; the UI receives only
sanitized aggregate counts, model hash and timing. No participant names,
transcripts, source filenames or local audio paths are exported by the UI.

## Bounded preparation and scoring

Run from the repository root. Default preparation prints a plan and makes no
request. An explicit download uses public file URLs without account tokens;
there is no hosted inference API:

```powershell
.\server\.venv\Scripts\python.exe scripts/prepare_public_human_speech.py
.\server\.venv\Scripts\python.exe scripts/prepare_public_human_speech.py --download --output-dir work/public-human-fleurs-new --per-language 10
```

The downloader never extracts archive paths to disk. It streams at most 16 MiB
of each archive, within a 100 MiB total body-byte limit, and stops after the
requested sources. Original full archives total approximately 2.31 GB; the
successful 50-source run consumed 48,667,201 body bytes, including metadata.
Exploration requests and the preserved partial run are separate from that
successful-run count. Existing output folders are refused; failures preserve
partial data and never trigger an automatic retry.

The first partial run collected Hindi then stopped at Tamil metadata. Its
literal TSV contains quotation marks that a CSV parser misinterpreted. The
corrected parser uses literal tab separation. That partial directory is
preserved as `work/public-human-fleurs-20261029/`; it is not part of the scored
sample. The dataset-viewer route also exceeded its parquet scan limit; original
publisher archives provide the bounded source path used here.

Default scoring is a no-access plan. Explicit execution validates every local
WAV, hash, declared source/licence, exact format and decoded-audio duplicates
before loading the installed, checksum-pinned CPU model once:

```powershell
.\server\.venv\Scripts\python.exe scripts/evaluate_public_human_speech.py --plan
.\server\.venv\Scripts\python.exe scripts/evaluate_public_human_speech.py --manifest work/public-human-fleurs-20261029-v2/manifest.public-human.jsonl --execute --output work/public-human-fleurs-20261029-v2/screening-study-02.json
```

Use a new report filename. The collector caps at ten sources per language; the
evaluator caps at 50 sources and 250 analysis calls, with two CPU threads.
The default 180-second admission budget stops new calls at its deadline; a
running synchronous load/analysis can finish later. Errors and unattempted
comparisons remain in the report, without automatic retries or policy changes.

## What is measured

Frozen experimental thresholds are allow at or below 0.2 and suspicious at or
above 0.8. Each source first supplies its opening **4.0375 seconds** as the native
baseline. Separate 0.5/1/2/3-second prefixes are repeated only inside the isolated
lab to fill the fixed model tensor. Repetition adds no observed speech. The
remainder of each 8–20-second source is not being certified clean.

Results show per-language false alarms, allowed clips, unknowns, errors,
unattempted analyses, classified coverage and CPU median/p95. All-source false
alarm fractions retain every source in their denominator; conditional rates
exclude unknowns and must be read with coverage. Neither is overall accuracy.
Model load, first analysis and warm analysis timings remain separate. CPU time
excludes speech collection, network, recognition, translation, synthesis and
listener playback; it is not end-to-end meeting latency.

**No synthetic clips are present.** AI detection rate, misses, overall accuracy
and preserved accuracy therefore remain unknown. This small convenience sample
does not establish performance in live Indian meetings or on unseen generators.
It can reveal a broken human baseline before spending on hosted translation or
attempting any shorter live input. The full live window and thresholds stay
unchanged. Independent synthetic-speech evaluation and real-device checks remain
necessary; voice cloning stays deferred.

Saved aggregate results appear on local **Performance** and **Audio lab** pages,
with an export separate from current room measurements.

## Observed result — 29 October 2026

All 250 bounded analysis calls completed in 64.57 seconds, with no errors or
unattempted comparisons. The model successfully scored 212 native tensors;
some shorter-prefix inputs abstained before native inference. Wrapper calls are
not an exact count of failed native inference attempts.

| Language | Human clips | Allowed | False alarms | Unknown | CPU median | CPU p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Hindi | 10 | 3 | 5 | 2 | 240.512 ms | 316.897 ms |
| Tamil | 10 | 3 | 2 | 5 | 242.456 ms | 256.444 ms |
| Bengali | 10 | 7 | 2 | 1 | 245.438 ms | 544.756 ms |
| Telugu | 10 | 6 | 1 | 3 | 283.891 ms | 728.145 ms |
| Marathi | 10 | 5 | 4 | 1 | 340.439 ms | 620.740 ms |
| All selected clips | 50 | 24 | 14 | 12 | 256.175 ms | See original report |

The full-window false-alarm fraction is **14/50 = 28%**, with **12/50 = 24%**
unknown and classified coverage **38/50 = 76%**. These descriptive clip fractions
are not overall accuracy or independent-speaker population estimates. They do
not meet a useful automatic-blocking baseline. Keep screening as experimental
monitoring while investigating preprocessing, domain mismatch, alternative
models and independently calibrated operating points; never tune on this final
evaluation subset or relabel its false alarms as synthetic speech.

| Observed prefix | False alarms / 50 | Unknown / 50 | Flags changed from native baseline / 50 |
| --- | ---: | ---: | ---: |
| 0.5 seconds | 7 | 31 | 40 |
| 1 second | 16 | 15 | 20 |
| 2 seconds | 20 | 15 | 16 |
| 3 seconds | 20 | 8 | 9 |

The lower 0.5-second alarm count accompanies far more abstentions; it is not a
demonstrated improvement. No shorter duration is approved for live enforcement.
Model loading took 1,100.578 ms; first analysis took 279.985 ms. Baseline CPU
median includes that first analysis, and neither metric is microphone-to-ear
latency. The JSON retains model, source and protocol provenance. Provider calls
and paid-server usage were zero throughout collection and scoring.
