# Evaluation and verification

The automated suite checks application behavior without provider keys. It cannot establish that a real microphone is transcribed accurately, a remote participant hears the correct audio, or a cloned voice resembles the consenting speaker. Those require an actual credentialed run and human listening.

An additional development verification script, `scripts/verify_routing.py`, connects actual local LiveKit participants and checks three-publisher/six-direction routing with synthetic provider fixtures. This exercises real WebRTC transport and recipient permissions; its generated tones and scripted provider responses do not establish Gnani recognition, translation or cloned-voice quality. Keep that evidence separate from a real provider evaluation.

## Included data

`evaluation/trade_cases.jsonl` contains a small synthetic set of purchasing utterances across Hindi, Tamil and Bengali. Each case includes a draft target translation, critical values and a meaning/negation check. These drafts are **unreviewed author examples**, not bilingual-validated gold labels. No personal speech, customer data or recordings are included. Do not quote an accuracy percentage on this set before qualified bilingual review. A short script is useful for smoke testing, not a population-level quality claim.

## Collect real results

From the project folder, with the live API running and credentials configured:

```powershell
python evaluation/run.py collect --api-url http://localhost:8000 --expected-mode live --output evaluation/results/live-run.jsonl
python evaluation/run.py template --output evaluation/review-template.csv
```

The collector checks server mode, creates a fresh two-member room per case, submits the actual typed source text, polls for the matching completed turn, records returned translation and timing, then leaves both memberships. It never invents a translation for failed requests. Running `collect` in live mode consumes the configured providers' credits. Credentials stay in the server environment; the output records neither membership nor LiveKit tokens.

Live collection submits processing consent for its synthetic test memberships. It never enrolls a cloned voice or opens a microphone. The included 18 cases exercise six Hindi→Tamil, six Tamil→Hindi, three Bengali→Hindi and three Hindi→Bengali phrases. English and the remaining pairings need separate evaluation cases before claiming equivalent coverage.

This is a **typed-text MT/TTS integration evaluation**. STT is bypassed intentionally. `server_pipeline_ms` comes from the single-turn room's reported metric. `request_to_result_ms` includes room setup, polling and client-to-server transport, and is not a first-audio latency measurement. Demo results are always labelled and excluded from live latency aggregates.

## Bilingual review

Give reviewers the source, target output and `reference_draft` side by side. Fill a copy of `review-template.csv`; duplicate a row with a different `reviewer_id` for a second reviewer. Set `source_fluent` and `target_fluent` to `yes` only when true. Use these fields:

| Field                        | Rule                                                                                       |
| ---------------------------- | ------------------------------------------------------------------------------------------ |
| `meaning_1_to_5`             | 1=commercial meaning wrong; 3=understandable with clarification; 5=all meaning retained    |
| `critical_values_correct`    | `yes`/`no`; quantities, amounts, names and identifiers match the source                    |
| `negation_condition_correct` | `yes`/`no`; refusal, only-if, before/after and conditions are preserved                    |
| `naturalness_1_to_5`         | 1=unusable wording; 5=natural and clear                                                    |
| `reference_approved`         | `yes`/`no`; approve the draft reference itself separately from the prediction              |
| `notes`                      | Explain mistranslations and acceptable variants; never paste credentials or private speech |

Reviewer language fluency is self-reported. Store their real consent/qualification record outside a public submission. Use two reviewers and adjudication for high-risk claims. A correct number on its own does not establish what that number refers to or whether a condition was reversed.

```powershell
python evaluation/run.py report --predictions evaluation/results/live-run.jsonl --ratings evaluation/reviewed.csv --output-dir evaluation/results/reviewed-run
```

Outputs are `case_report.csv` and `summary.json`. They keep unreviewed cases explicit, do not infer semantic accuracy from string similarity and exclude demo/failure values from live timing. The numeric surface check only converts Unicode decimal digits and checks whether required numeral values appear. Spelled-out numbers may trigger manual review, and repeated/wrongly associated numbers may pass; review all flagged and apparently passing cases. Human ratings apply only to the exact prediction file the reviewer saw: do not reuse a ratings CSV after regenerating outputs.

## Actual voice and browser acceptance

Run these with two or three real browser contexts and fresh credentials before submission:

1. Hindi A speaks while Tamil B listens; repeat in reverse; add Bengali C. Confirm each listener hears their selected language and the speaker does not hear their own translation.
2. Add two listeners with the same language. Confirm one synthesis per unique language and both intended recipients receive it. Test two participants with the same source/listening language.
3. Speak quantities, ₹ amounts, negation, conditional dispatch and an unfamiliar business name. Review the original audio, STT transcript and each target translation separately. Wrong STT cannot be repaired by merely comparing target numbers.
4. Measure phrase-end to first audible translated sample at the receiver using synchronized capture/instrumentation. Record hardware, browser, network, endpoint, voice mode and segmentation settings. Report p50/p95 plus sample count. Do not replace this with server timing.
5. Try mic denial, device removal, autoplay restriction, reconnect, provider timeout, one member leaving mid-turn and a saturated queue. Confirm understandable recovery and no stale audio after leaving.
6. Enroll a clean, consented spoken reference; compare stock and cloned target speech. Let the speaker judge similarity; bilingual listeners judge intelligibility. Confirm rejection/deletion and ownership isolation. A reference waveform check is not a consent or identity proof.
7. Inspect actual LiveKit track subscribers: originals only to the agent; translations only to intended recipients. Exercise join/leave/language changes. A UI badge alone is not media-routing evidence.

## Reproducibility record

Attach the app revision, dependency lockfiles, actual configured provider/model identifiers, region inventory, anonymized result files, reviewer protocol, failure count and exact latency boundary. Document provider account access separately. The official [Gnani challenge guide](https://www.gnani.ai/resources/blogs/great-indian-ai-internship-challenge-2026) distinguishes hosted Prisma/Timbre from Evon weights requiring access and hosting. Verify actual entitlement before a live demonstration. Do not claim India-only processing solely because a model provider is Indian; see the deployment boundary in [ARCHITECTURE.md](ARCHITECTURE.md).
