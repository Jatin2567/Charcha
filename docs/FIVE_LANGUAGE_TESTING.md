# Five-language latency pass, then screening

For the current bounded conference delivery and listener checks see
[Five-language conference calls](FIVE_LANGUAGE_CALLS.md). This longer
latency-study proposal has no spending authorization.

This is a prepared test protocol, **not a live E2E result or a provider approval**. It covers Hindi (`hi`), Tamil (`ta`), Bengali (`bn`), Telugu (`te`) and Marathi (`mr`) with standard voices. Voice cloning stays deferred. The first pass uses two participants at a time with deepfake screening off. The separate [screening protocol](FIVE_LANGUAGE_SCREENING.md) follows review of the latency evidence.

## Coverage and draft prompts

There are 20 directed language pairs, including both directions for every pair. Each pair has one planned cold-route trial and two planned repeat trials: **60 proposed spoken STT → Evon MT → standard TTS observations**. This is pairwise coverage across five languages, not five simultaneous participants. It does not replace a later multi-party fan-out test.

Source prompts, intended meanings and target voice names come from `scripts/plan_language_matrix.py`. A source-language speaker must check the drafts before paid testing. English meaning notes are review aids, not trusted target-language translations.

| Source language | Draft focus | Check during bilingual review |
| --- | --- | --- |
| Hindi | Meeting time | Preserve 10, reject 11, do not invent a date/time zone. |
| Tamil | Book colour | Request the blue book and reject red. |
| Bengali | Relative day | Preserve tomorrow morning at 9, library, and rejection of today. |
| Telugu | Decimal and unit | Preserve 1.5 litres and rejection of 150 millilitres. |
| Marathi | Past tense | Preserve meeting in the park yesterday evening as an event that already happened. |

The target voices are Nalini (Hindi), Trisha (Tamil), Kirra (Bengali), Suhana (Telugu), and Zahira (Marathi), using the existing `timbre-v2.5` standard-voice plan. Account acceptance, current serving configuration and meaning quality remain unverified until the exact bounded flow runs. A catalog entry is not a successful live test.

## Offline artifacts

Run either command from the repository root. Both print data only; neither opens credentials, reads the environment, touches the usage ledger, creates a provider client, starts a cloud resource, records audio, or approves a flow.

```powershell
& server/.venv/Scripts/python.exe scripts/plan_five_language_test.py --plan
& server/.venv/Scripts/python.exe scripts/plan_five_language_test.py --review-csv
```

The generated copies are:

- `web/src/data/fiveLanguagePlan.json`: deterministic, nonsecret UI data, with every result pending.
- `work/five-language/plan.json`: the same plan for a local run folder.
- `work/five-language/review.csv`: 60 rows with draft text, stable trial IDs, hashes and blank review/measurement columns.

The plan hash covers all prompts, meaning notes, standard voices, settings, caps, price references and proposed trials. Each trial also binds its route hash and its own limits. Correcting a prompt or changing limits requires a new generated plan and review of the changed proposal. Hashes establish what was proposed; they do not authorize it. Keep actual run evidence in a separate copy, preserving the original blank template.

## Budget and flow limits

The latest user authorization is **₹5,000 total GCP resource cost for the project**, with **₹2,500 as the latency-stage GCP subcap** and ₹2,500 reserved for later work. These are GCP ceilings, not a speech-provider grant. Confirm the chosen GPU's current price, other resource charges, remaining stage/project allowance, quota and bounded runtime before starting it. Configure an automatic stop; budget alerts alone do not stop a server. Do not assume promotional-credit availability or a provider invoice amount.

Every speech trial remains individually unapproved, including repeat trials. An approval proposal identifies its trial ID/hash, source/target languages, exact draft prompt, standard target voice, screening-off setting and these caps:

| Resource | Maximum per proposed flow | Maximum for all 60 proposals |
| --- | --- | --- |
| STT | 1 connection; 15 connected seconds including handshake/idle | 60 connections; 900 seconds |
| Evon MT | 1 request; 500 source characters | 60 requests; 30,000 source characters |
| Standard TTS | 1 request; 300 output characters | 60 requests; 18,000 characters |
| Voice enrollment | 0 | 0 |
| Automatic retries | 0 | 0 |

The existing approval expiry is proposed as 120 seconds; **that is not permission to leave STT connected for 120 seconds**. Its STT allowance remains 15 connected seconds. Speak the phrase once and mute/close the source flow promptly. An utterance that splits into extra finalized STT segments may exhaust the one-MT/one-TTS limits; retain that failure for review instead of granting more usage. Over-limit text must be rejected, not silently truncated or charged through another flow.

Using only the user's ₹27/STT hour and ₹27/10,000 TTS characters reference:

- STT maximum reference: 900 ÷ 3,600 × ₹27 = **₹6.75**.
- TTS maximum reference: 18,000 ÷ 10,000 × ₹27 = **₹48.60**.
- Combined speech reference for all proposed caps: **₹55.35**; one maxed trial is ₹0.9225.

This excludes provider billing rounding, tax, GPU/other GCP charges and any additional trials. It is not an invoice, programme-credit conversion, current credit balance, or bulk authorization. Keep actual provider usage units, reference estimates and verified billed amounts separate; leave unknown amounts blank. Stop before any next trial whose conservative remaining resource cost cannot fit within the relevant GCP ceiling. Failures/replacements need fresh review and, when paid, fresh flow approval.

## Run sequence after infrastructure is available

1. Review source drafts and intended meanings with source-language speakers. Verify the GPU quota, model/image revisions, model readiness, five-language configuration, explicit shutdown time and conservative GCP cost. Do not spend speech credits merely checking configuration.
2. Join two users. Both use headphones. The source speaks the selected source language; the listener selects the target language and stays muted. Use standard voices and screening **off**. Verify the listener subscribes to the intended target track and the source cannot hear its own translated output.
3. Review and approve only the next identified trial, then speak its source phrase once. Mute/close its source flow within the 15-second STT allowance. Record any timeout, cap rejection, missing transcript, wrong routing or provider error in that row. Do not silently replace a failed observation or automatically retry it.
4. For each directed pair, collect one planned cold-route observation and two separately approved repeat observations. Keep the GPU model loaded only within the bounded session. Record whether room/track/subscription state was actually recreated, retained or unknown.
5. Export the room's Performance samples and Usage evidence. Match each row to flow ID, performance-sample ID and route. A manual listener/bilingual reviewer records audible target speech, meaning, numbers, negation, units and original/self double playback. Source transcription and target meaning are separate checks.
6. Review all 60 scheduled outcomes, including errors, cancellations and missing markers. If any route is incomplete or cannot be understood, report it as incomplete; an attempted matrix is not a successful E2E matrix.
7. Run the [separate screening protocol](FIVE_LANGUAGE_SCREENING.md) with consented genuine and independently labelled spoof material after the latency review. Do not infer deepfake detection accuracy from latency results or synthetic unit-test tones.
8. Repeat accepted routes on two physical devices with an explicitly trusted HTTPS connection before claiming two-device acceptance. Windows certificate trust was deferred by the user; this plan does not install or bypass it. Multi-party tests and voice cloning are later gates.

“Cold route” means a newly joined route/output path while the GPU model is already loaded. GPU allocation, download and model initialization are separate startup metrics. “Warm repeat” is a planned condition, not an inferred measurement: if muting/unmuting recreates a track or the room was rejoined, write that observed state in the row and do not claim warm transport.

## Measurements and acceptance evidence

The blank CSV deliberately distinguishes existing server measurements from audible listener delay:

| CSV field | Evidence and boundary |
| --- | --- |
| `queue_ms` | Server application queue wait. |
| `stt_processing_to_transcript_ms` | Provider processing event → final transcript; leave blank when no processing marker arrives. This excludes any unobserved acoustic/VAD delay before that event. |
| `mt_ms` | Application translation-request timing. |
| `tts_first_pcm_ms` | Synthesis/output-path start → first server PCM, including relevant output/subscriber readiness waits in the existing measurement. |
| `server_queue_to_first_pcm_plus_stt_ms` | Queue entry → first server PCM plus available STT marker duration. Mark it partial if STT is absent. It is not microphone-to-listener delay. |
| `listener_phrase_end_to_audio_onset_ms` | Actual listener audio onset minus source phrase end from one consented common-clock recording, with the method and evidence ID stored. |

For audible delay, record source speech and listener playback on the same recording clock with consent, then annotate the source phrase end and target audio onset. If a safe common-clock measurement is unavailable, leave listener delay blank. Do not subtract browser timestamps from different devices. Recording artifacts containing voices stay private, separate from the checked-in plan.

Show individual observations, actual setup states and attempted/completed counts for every direction. A descriptive median may be shown alongside its sample count; **three trials per pair, including only two planned warm repeats, cannot establish a reliable p95 or a latency SLA**. Keep server/listener and partial/complete measurements distinct. Stage percentiles cannot be added to obtain a total percentile.

A complete latency test requires actual provider calls, audible correct target-language output, matched Usage/Performance evidence and manual meaning review. One draft prompt per language provides smoke coverage, not translation accuracy or a general language-quality benchmark. Screening remains unmeasured until its own separate protocol passes; cloning remains deferred.
