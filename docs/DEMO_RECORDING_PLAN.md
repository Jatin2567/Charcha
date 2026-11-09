# Charcha — 60-second recording plan

## Current outcome — supersedes the historical plan below

The final candidate is `work/demo-video/story-v11/Charcha-60-second-final.mp4`, verified at 60 seconds and 1920×1080. A later approved attempt completed provider processing, saved in `work/demo-video/live-evidence-2/`. V11 reuses that Hindi→English audio with a typed correction, automated acknowledgements and actual UI replay. Source speech is synthetic; presentation copies run at 85% speed. The film makes no live latency or human comprehension claim.

The current Codex stop threshold is **2% remaining**. Earlier approvals below are historical, consumed limits, not permission for another run. Final edits/checks use no new Gnani or Modal calls. Follow [the final submission package](SUBMISSION.md) for current wording and remaining links.

## Historical first attempt and preparation (superseded)

Updated 9 November 2026. The owner approved the bounded request counts below and up to $3 Modal usage, with owner-monitored Gnani cloning charges, and then lowered the Codex stop threshold to **10% remaining**.

## Attempt outcome

The isolated two-account UI rehearsal passed correction versioning, separate listener acknowledgement, recap saving and WhatsApp preview. The approved Modal test was deployed, but its single readiness request timed out after 360.023 seconds. The test app was stopped and the immediate billing snapshot showed $0 additional metered usage; this is an observed snapshot, not a final invoice. **No Gnani requests, translations, enrollment or cloned-speech requests were made.** No retry was attempted. The existing serverless production deployment was not changed.

A 60-second, 1080p offline workflow preview has been rendered from actual UI captures, scripted example text and free local presentation narration: `work/demo-video/Charcha-60-second-workflow-preview.mp4`. It is visibly labelled offline throughout and must not be submitted as evidence of a live provider conversation. The version containing new real provider audio is blocked by model readiness. The receipts, captions and capture scripts are under `work/demo-video/` (local, ignored by Git).

The revised story version is `work/demo-video/story-v2/Charcha-60-second-story-preview.mp4`: three fictional workshop volunteers, sourced Census 2011 / MoSPI 2025 context, the correction-and-confirmation workflow, and a brief gallery of application pages. It is exactly 60 seconds at 1920×1080, with full decoding verified, English captions and a sources/scope note alongside it. It remains an offline Hindi–English UI illustration, not a three-language live test. No additional provider calls were used. The owner confirmed the reported repeated interpretation was microphone pickup from another device's speaker; the investigation-only edits were removed.

## Product story

One instruction, one corrected detail, one visible acknowledgement and a record both sides can keep. Use Hindi→English for the automated demo so international viewers can follow the output. The separate Hindi–Telugu human-review rehearsal remains prepared; this video does not establish native-speaker acceptance.

Use two test identities on independent browser profiles. Clearly label the footage **Scripted test accounts · actual provider processing**. Automated confirmation demonstrates the acknowledgement feature; it is not an independent person's endorsement or comprehension result.

Charcoal background, royal-blue accents, existing Charcha waveform mark, readable captions and two restrained zooms. Let the genuine source/output audio carry the middle of the video. The model-generated voice is a fictional test voice, not a person impersonated or a claim of measured voice similarity. Verify reference-sample compatibility before approval; do not invent a successful enrollment if the provider rejects it.

## Capture and edit

| Seconds | Footage | Sound / message |
| --- | --- | --- |
| 0–5 | Charcha title and Hindi→English labels | “Different languages. One shared understanding.” |
| 5–23 | Actual test-account call, Hindi source, translated audio and captions | Source: “नमस्ते। कल की बैठक के लिए शाम चार बजे कमरा तीन में बारह नीली फाइलें लाना।” Let real output play, with narration paused. |
| 23–39 | Correct for everyone, room 3 changed to room 4 | Replace full message: “कल की बैठक के लिए शाम चार बजे कमरा चार में बारह नीली फाइलें लाना, कमरा तीन में नहीं।” Show the new translation and pending acknowledgement. |
| 39–49 | Listener test account confirms the corrected turn | “The earlier acknowledgement stays with the earlier words.” Show the new confirmation separately. |
| 49–60 | Bilingual recap and PDF/WhatsApp preview | “Keep what was said, corrected and understood. Built using Gnani AI.” |

These are intended edit windows. If actual processing exceeds them, use labelled cuts outside the measured exchange and retain an uncut recording. Never accelerate output or manufacture latency. Include a measured result only when collected with its boundary and sample count; otherwise show a feature outcome without a number.

Capture system output and source audio separately, amplify quiet audio, and lower/remove music during speech. Preserve source timing and voice character. AI may create narration and presentation graphics; it must not replace the app's translation with an invented successful answer. AI narration is optional and any external generation charge needs a separate quote. Local editing can be free of provider charges.

## Approved single-run usage envelope

- One source speaker and one listening test account; only the source is enrolled. No listener speech/read-back in this automated version.
- At most one standard Hindi TTS request, 300 characters, to create a fictional source/reference clip. Use the same generated sample as the consented test reference and injected source; check that it satisfies the 5–30-second upload requirement. A failure stops the attempt, without an unapproved regeneration.
- One voice-embedding request; two translated turns (original speech and typed correction); at most two cloned synthesis deliveries, 600 output characters total and 600 source characters total.
- One STT connection, at most 25 connected seconds. No source-generation, enrollment or provider retries. Unexpected STT segmentation or partial delivery counts against the limit; stop instead of silently adding turns.
- One A100 80 GB container, 4 CPU cores, 64 GiB memory; at most 20 connected minutes including startup, then release the room and verify scale-down. Reserve another 120 seconds for idle scale-down, which is provider-controlled. If model readiness takes over six minutes, stop this attempt.
- Complete layout, login preparation, recorder checks and local rehearsals before connecting interpreted media. A muted interpreted connection can still start compute. Confirm other meetings are not holding the shared GPU before attributing usage to this run.
- During execution observe the unit counts and stop at the proposed envelope. This is an operator procedure, not a provider-enforced monetary cap. Do not start until the permitted charge treatment is agreed.

## Cost estimate

Using the owner's supplied standard rates, source TTS ≤300 × ₹27/10,000 = **₹0.81**; STT ≤25 × ₹27/3,600 = **₹0.1875**. Known subtotal **₹0.9975**, approximately ₹1.

**Voice enrollment and cloned synthesis prices are unverified.** Total Gnani charge is that subtotal plus one embedding request and up to 600 cloned-output characters. No reliable all-in rupee amount can be quoted yet. If, and only if, cloned synthesis shares the standard rate and enrollment is free, the arithmetic would be ₹2.6175; this is a conditional example, not a verified quote. Provider rounding/taxes and programme-credit conversion may differ.

Modal pricing checked 9 November: A100-80 GB $0.000694/s; CPU $0.0000131/core/s; RAM $0.00000222/GiB/s. Resource baseline = $0.00088848/s. Broad `ap` has a 1.15× region multiplier. A 22-minute calculation is approximately **$1.35**. The project's conservative 1.75× reserve yields **$2.06**, rounded upward; adding $0.50 incidental allowance gives **$2.56**. Propose **$3 of Modal credits for this single recording attempt**, including startup, not merely the 60-second edit. This reserve is not a guaranteed cap; check actual metering and stop/release compute promptly. Existing GCP hosting continues separately.

Sources: [Modal pricing](https://modal.com/pricing), [region multipliers](https://modal.com/docs/guide/region-selection), [Gnani embedding API](https://docs.gnani.ai/api/VC/voice-clone-embeddings), [cloned synthesis API](https://docs.gnani.ai/api/VC/vc-websocket). The two cloning API pages document the calls but do not establish the account's charge rates.

## Required before the live recording

The owner has approved the bounded request counts with owner-monitored Gnani billing and the $3 Modal allowance. Do not request the same approval again unless the scope changes or the allowance is consumed. Test-account identity/access setup, recording tools and the generated reference's suitability must still be checked before the paid run. Until then, prepare only an explicitly labelled offline UI rehearsal; it is not the final working-provider demonstration.

The owner renewed the stop threshold to **10% remaining Codex allowance** on 9 November. Stop immediately at that threshold, even if recording/editing is unfinished. Provider request limits and the $3 Modal ceiling are unchanged. Preparation is not successful execution or a promise of an award.
