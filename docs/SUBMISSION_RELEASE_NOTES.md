# Submission publication record

## Verified follow-up: `reviewer-reporting-20261110`

- Separated personal reviewer activity from shared workspace usage. Personal reports read the signed-in account's persistent attempted-unit ledger, use UTC daily boundaries and show unknown values when storage is unavailable. They never substitute the owner's activity or infer provider balances/prices.
- Added an explicit ledger selector and scoped interpretation-engine reporting. Current meetings use their selected endpoint; multiple personal engines do not receive an invented aggregate readiness or startup measurement. Report/status reads do not start provider calls or compute.
- Hardened reviewer teardown so access/credentials are invalidated and cleanup of remaining resources is attempted when one cleanup action fails; deferred media teardown can be retried. Normalized uppercase room codes in engine GET/POST routes to match membership authentication.
- Corrected the media verification record's stale publication wording and older pitch hash. The published films, caption timing and approved-feedback PDF are unchanged; their hashes and package copies were independently checked. Sathvika's full review still includes her response-latency observation.
- Updated the [reviewer guide](REVIEWER_GUIDE.md) with ledger scope, UTC/zero/unknown meanings, usage-history persistence and current-versus-saved engine reporting. Desktop/mobile browser checks used the actual local API with provider responses mocked and verified personal/shared activity and engine scope; no Gnani/Modal calls were made.
- Final full backend: **1,579 passed, one skipped, in 224.65 seconds**. Frontend: **335 passed across 47 files**; seven runtime checks and production build passed. The final focused reporting run passed eight cases: seven overlap full-suite coverage and one uppercase-code case was added after full-suite collection. These counts must not be summed.
- Deployed tested code commit `d0091916cc29c3a1cd1a4375d5db9fbc4c9f340e`. At **2026-11-10 16:31:03.205358 UTC**, health returned 200, new Reviewer/Prejoin/Usage/Performance components were present, identity was configured, and protected anonymous endpoints including usage/account engine returned 401. At **16:31:12.692545 UTC**, all 43 deployed source-file hashes matched, with no extra or missing files. No real reviewer invitations were issued, no authenticated live provider flow was exercised and no Gnani/Modal calls were made. This verifies deployment and application boundaries, not provider quality, actual billing or physical speech-to-ear latency.

## Source revision: participant feedback and reviewer setup, 10 November 2026

- Added Sathvika's approved full review, attributed to a tech student and Telugu speaker, in the submission guide and one-page pitch. Only sentence spacing changed; her response-latency observation remains intact.
- Rebalanced the one-page pitch, rendered it with Poppler and checked its layout. The historical test counts and provider-stage measurement boundaries remain dated and explicit.
- Added the [reviewer setup guide](REVIEWER_GUIDE.md) and README entry for private authenticated invitations, shared or reviewer-owned provider resources, and explicit bounded preparation before joining. The matching application release was deployed and checked on 10 November.
- Refreshed the local submission archive, adding the full feedback text and reviewer guide. Existing video files are unchanged. This media/PDF preparation made no Gnani requests or Modal sessions and did not post socially or submit the form. The subsequent application deployment is recorded below.
- Final local reviewer-release checks on 10 November passed: 1,558 backend tests, one skipped (194.81 seconds); 328 frontend tests across 47 files; seven runtime checks and the production build. The separate generator suite passed 40 tests with two platform skips. Desktop/mobile reviewer walkthroughs also passed, with mocked provider responses and zero provider calls. Hosted deployment remains separately recorded; these results do not certify live provider quality or speed.

### Hosted release `reviewer-preparation-20261110`

Final verification at 10 November 2026, 16:01:36 UTC passed: health 200; updated reviewer/prejoin bundles, admin invitation controls and privacy content; configured identity; anonymous protected endpoints denied with 401; all 13 checked deployed source-file hashes matched. The API was in live mode with shared serverless configuration enabled. These settings do not mean the GPU was started. No invitations were issued, no authenticated live provider flow was tested and no Gnani/Modal calls were made. Reviewer-owned providers still need the Charcha application, identity and LiveKit hosting to remain available. Sanitized results are in [release verification](REVIEWER_RELEASE_VERIFICATION.json).

## 10 November 2026 — music/portal assets included in this revision

- Prepared and verified a 2:40 build film and 60-second social story featuring fictional Asha (Hindi), Ravi (Telugu) and Meher (Punjabi). The story uses actual app screens from a scripted three-account rehearsal and prepared standard-voice readings; it is not a new live three-device translation benchmark or cloning test.
- Added quiet original background music synthesized locally, with speech reused from existing approved recordings. The refresh makes no new Gnani or Modal calls.
- Captured offline portal views for Home, Prejoin, Performance, Voice Studio, Test lab and Audio lab, alongside the meeting and recap workflow. The local workflow, final encoded frames, full decoding, audio peaks and subtitle timing were checked for the new files.
- Retaining the separately dated 9 November 3.94 s and 4.23 s translation-to-first-decoded-audio examples, with their measurement exclusions. VoiceShield remains experimental.
- Refreshed the one-page pitch and linking the new filenames in the submission materials. Corrected product/setup/architecture descriptions for host admission, required consented voice enrollment, saved reports and meeting-driven inference; removed unsupported latency and agreement promises from Home.
- The production build, seven runtime checks and offline three-account rehearsal passed during the media-only preparation pass. Full application suites were not rerun in that earlier pass; reviewer-release checks are recorded separately in the final submission review.

This source revision includes the refreshed media, pitch and copy. Final hashes and verification records identify those exact files. Source publication must be checked against its actual commit; it does not deploy the hosted application, publish a social post or submit the challenge form. The earlier verified public release was commit `d4a8020befa4d7d367cf64e2dd17041e5a4a434f`; the historical notes below refer to that release.

## 10 November 2026 — earlier published release

- Replaced unsupported market statistics, zero-delay claims and overstated sovereignty/recap guarantees with code-backed descriptions.
- Corrected dated test counts and separated partial server timings from listener latency.
- Improved the one-page pitch and reviewer-facing media links.
- Refined the demo around changed instructions, fresh acknowledgements, bilingual records and shared target-language routing.
- Mapped ten award categories to evidence or actual eligibility requirements; no all-awards qualification claim.
- Preserved existing Git history. New commits use their actual creation time; no backdated activity was introduced.

The videos replay saved provider output with synthetic test speech and labelled UI. Application checks quoted in the pitch are dated 9 November. This publication pass uses no Gnani or Modal requests. Media verification is separate from application validation.

The production build and all seven runtime checks passed again on 10 November. Both earlier videos passed full decoding, and the 2:30 film's 22 subtitle cues were ordered without overlap. These historical checks do not certify later media refreshes.

The final independent reviews found no substantive claim or packaging blocker. The public GitHub About description was corrected, publication wording was aligned and the [final checklist](FINAL_SUBMISSION_CHECK.md) was added. Submission of the form and social publication remain with the owner.

Private environment files, runtime databases, generated secrets, model weights and operator recordings remain excluded from Git. Publication checks are a bounded credential-pattern review, not a comprehensive security certification.

Source/media publication does not submit the competition form or post on social media. The owner completes those steps using the [submission guide](SUBMISSION.md).
