# Live submission rehearsal — preparation only

Prepared 9 November 2026. **Not executed. No live language, latency, confirmation or persistence result is claimed.**
The companion [results sheet](../evaluation/submission_rehearsal_results.csv) contains planned cases; all observed outcomes are blank.

## People and order

| Pair | Role and readiness | Review requirement |
| --- | --- | --- |
| Hindi ↔ Telugu (`hi-te`) | Main demonstration; Telugu speaker is available | Hindi host plus a fluent Hindi–Telugu reviewer; the speaker may review after their blind readback |
| Hindi ↔ Tamil (`hi-ta`) | Prepared language test | Run only with an actual fluent Tamil speaker and Hindi–Tamil review; do not substitute a person reading unfamiliar Tamil |
| Hindi ↔ Punjabi (`hi-pa`) | Prepared; prospective speaker, pending review | Confirm Punjabi fluency/availability and Hindi–Punjabi review before scheduling |

Use two consenting adults, two devices and separate signed-in identities: **A**, Hindi host; **B**, target-language speaker/listener.
A bilingual reviewer may observe beside them without joining the room, so the plan has only two participants.
Do not claim independently reviewed target-language accuracy from the system's Hindi back-translation alone.
Use fictional everyday office coordination, not a commercial transaction. Participants may decline recording or voice setup.
Give B only the instruction “Listen, then say back what you understood in your own language.” Keep this answer key and Hindi prompts out of B's view until both readbacks finish; app-generated captions are allowed, but record whether they were used.

## Preparation boundary and proposed resources

No Gnani/Modal call, server start, deployment, credential change, enrollment or interpreted-room connection is authorized by this document.
Before separate authorization, preparation is limited to offline transport rehearsal and read-only local settings/status review; this task starts no services.
**Connecting an admitted participant to hosted interpreted audio starts serverless GPU preparation even while muted. Voice enrollment calls Gnani.** Do not join to “just check” readiness.
Read [current operating policy](ON_DEMAND_MEETINGS.md); historical standard-voice canaries and old budgets are not permission for this personal-voice drill.

After separately authorized, run one pair at a time in a **fresh room**, with new consented own-voice enrollment for each speaker in each room. Never reuse another person's sample.

| Proposed maximum per pair | Limit |
| --- | --- |
| Joined participants / enrollments | 2 / 2 attempts, one own-voice clip each, 5–10 seconds per clip |
| Conversation | 4 spoken turns plus 1 typed replacement; each spoken turn ≤10 seconds |
| STT | At most 4 microphone windows/connections, ≤30 seconds each; ≤120 connected STT seconds total |
| Translation and cloned synthesis | At most 6 translated listener branches and 6 cloned synthesis attempts, including partial/error branches |
| Text volume | ≤300 source and ≤300 target characters per branch; ≤1,800 of each across the room |
| Connected wall clock | ≤10 minutes from first audio connection, including startup; stop if readiness takes >6 minutes |
| Retries / repeats | 0 automatic retries; no manual rerun or extra phrase under this proposal |

Five planned branches leave one branch for unexpected segmentation, not a spare retry. Keep only the intended source microphone open; do not mute it until output completes because muting can cancel pending work.
The operator must be able to observe/enforce these proposed caps before proceeding; they are not a claim that the app implements a monetary ceiling. Stop on a failed setup, unexpected extra branch, cap, or provider error; log it without retrying.
At each turn allow at most 20 seconds after speech end (or typed submission) for output; mark missing output `timeout` and leave its latency blank.
All three pairs, if later individually authorized, total at most 6 enrollment attempts, 12 spoken + 3 typed turns, 360 STT seconds, 18 branches and 30 connected minutes. This is not a batch authorization.
Gnani clone/enrollment pricing is unverified: **no rupee estimate or provider-credit approval is presumed**. Startup, silence and provider-controlled scale-down also consume compute; 10 connected minutes is not a billing ceiling.

## The five-turn drill, repeated for each prepared pair

Before speech, record room/pair, consent references, device/browser, actual listening languages, own-voice setup state, VoiceShield mode and recorder setup. Keep call tabs visible and prevent echo.
After authorized startup, wait for actual ready state; record startup separately. Use one shared-clock recording only with both participants' agreement.

Before the measured turns, refresh B's meeting tab once. Check the same admitted participant returns without a second host approval or voice enrollment, captions restore, and microphone/camera remain off. Enable playback if the browser asks. Record `refresh_recovery` separately; do not count this as a translation attempt. This stays inside the proposed connected-time limit.

| Case | Actor / input | Action and reviewer-only expected meaning |
| --- | --- | --- |
| S1 | A speaks Hindi | **“कल शाम 4 बजे कमरा 3 में 12 नीली फाइलें लाना।”** Tomorrow, 4 p.m., room 3, bring 12 blue files. |
| S2 | B speaks target language | Independently read back S1 in natural Telugu/Tamil/Punjabi, without an expected translated script. A listens to the Hindi output; reviewer checks B's actual utterance. |
| C1 | A types a correction | On S1 choose **Correct for everyone**; replace the entire source message with **“कल शाम 4 बजे कमरा 4 में 12 नीली फाइलें लाना, कमरा 3 में नहीं।”** Then **Share correction** once. |
| S3 | B speaks target language | Independently read back the corrected instruction, including **room 4, not room 3**. Reviewer checks what B actually said; A checks Hindi output. |
| S4 | A speaks Hindi | **“ठीक है। कल शाम 4 बजे कमरा 4 में 12 नीली फाइलें लाना, कमरा 3 में नहीं।”** B checks the final audible instruction. |

Use seven detail slots: **day, time including p.m., destination, count, colour, object/action, exclusion**. For S1/S2, exclusion is “none stated”; for C1/S3/S4, “not room 3” must be explicit. Final destination is room **4**, never room 3.
The host and bilingual reviewer score each slot 0/1 against the intended message; record 0–7, actual wording and any omission/addition. Record STT, target caption, target speech and reverse Hindi separately in notes when they disagree.
Do not coach B or silently fix a readback. A bad readback is a result; a fluent person's later explanation is review evidence, not a replacement successful attempt.

## Confirmation checkpoints on both devices

1. Before S1 confirmation, expand **Who confirmed understanding?** on A and B: B is `Not yet confirmed`; A, the author, is not an eligible listener. Capture that state, then B confirms only if understood.
2. Before C1, capture S1 with B `Confirmed understanding`; A confirms S2 only if its Hindi output is understood. A confirmation means understanding, not agreement or verified translation accuracy.
3. After C1 arrives and **before** B confirms it, inspect both devices: S1 remains visible as replaced with **Earlier acknowledgements**; its old confirmation remains historical. C1 is a separate corrected message with B `Not yet confirmed`. The old click must not carry over.
4. After S3 readback is recorded, B confirms C1 only if understood; A confirms S3 only if understood. Capture both views again, linking original and corrected turn IDs.
5. On S4 capture B pending, then B confirmed if understood. Record each eligible participant separately; no listener list or failed/incomplete output must not be described as unanimous confirmation.
6. Eligibility uses listeners present when the turn was submitted, not later arrivals. No extra join/leave case is needed for this two-person drill; report unknown/legacy states as unknown. Completed current messages alone can reach the all-listeners-confirmed state.

## Timing: preserve the boundary

- **Spoken S1/S2/S3/S4:** primary physical latency is `(first translated listener-output sample − first sample after last voiced source sample) / sample rate × 1000`, using one recording clock. Review the audio and waveform; retain recording hash, sample positions, capture tap and annotation uncertainty in private evidence. Ambiguous onset, overlap or absent capture stays unmeasured.
- A single continuous phone recording is acceptable if the source and translated output are distinguishable; an isolated two-channel recording is better. Do not subtract unrelated device wall clocks. See [capture instructions](SPEECH_END_LATENCY.md).
- **Typed C1:** measure **Share correction submission → first translated listener output**, using one observable clock (for example one continuous screen/audio capture). Label `typed_submit_to_output`; never mix it with speech-end latency. No suitable capture means blank timing.
- Performance's server-ingress speech-end estimate and calibrated decoded-receiver observations are separate measurements, with their displayed uncertainty. Neither measures microphone uplink plus physical speaker output. Server processing / Evon-only time is not listener latency.
- Record first-route/warm/startup conditions and actual personal-voice/VoiceShield settings. The older standard-voice, screening-off engineering target is not a passed gate for this drill. Report individual observed values and counts; this tiny sample establishes no p95 or general latency/accuracy claim.

## Recap, save, re-login and export checks

After both participants explicitly leave, each reviews their own recap. Record any error or missing turn instead of rebuilding the record manually.
Verify original S1, replaced marker, C1 corrected marker, both wordings and per-person acknowledgements survive. The current set should be S2/C1/S3/S4 when all five turns exist; S1 must not inflate current-message confirmation totals.
For each participant choose **Save recap**, verify **Saved on this device**, refresh, then sign out and back in as the **same identity on the same browser/device**. Open History and recheck the corrected wording and confirmation states. Recaps are explicitly saved, account-scoped device-local records; this does not establish cross-device sync.
Export **Download transcript**, **Export JSON** and **Save PDF / Print** locally; open the files. Confirm both versions, readable Hindi/target script, participant names, missing-translation labels and exact confirmation states. Select the target recap language; exports use stored translations and do not generate new ones. Do not send the WhatsApp preview or exports to anyone.
Separately, each participant opens **Performance → Meeting report** for this room, records pending/saved/retrying status, and checks the saved report after same-account re-login. These account-persisted reports contain metrics, not the transcript; receiver/connection snapshots belong to their own account. Do not restart a server to test persistence.
Last explicit departure releases the occupancy hold; record departure time and any read-only shutdown observation. Provider scale-down is delayed and must not be presented as immediate or free.

## Filling the results sheet and reporting honestly

`plan_state=planned_not_executed` describes preparation, not an outcome. Blank measured fields mean **unknown/not measured**, never zero, false or success. Fill `execution_status` only after the case is attempted (`complete`, `error`, `timeout`, `unmeasured`, or `blocked`); a blocked precondition is not a translation attempt.
Use pseudonymous participant/reviewer IDs. For observation rows, `role` is the operator/subject; the source/target columns identify the route. Keep raw audio, private identities and consent evidence outside version control; place only safe evidence references in the CSV.
Populate per-case IDs, actual observed text, score, acknowledgement states, timing kind/uncertainty, usage and artifacts as applicable. In the `connect_startup` row, record actual aggregate enrollment, STT, translation/synthesis usage and connected seconds for that pair. Additional timing boundaries require separate rows tied to the same `attempt_id`, not extra attempted turns.
For any later separately authorized rerun append a new attempt; preserve the failed original. Do not overwrite an error with success or import historical canary timings into these rows.
Report **delivered attempts / all initiated translation attempts**, including failed, timed-out, cancelled and partial attempts in the denominator. Also report fully correct attempts / all initiated attempts, reviewed attempts / all initiated attempts, and measured acoustic attempts / all initiated spoken attempts; unknown meaning cannot pass. Keep typed and spoken denominators separate and name every denominator.
Report confirmation checkpoints and recap/export/persistence checks as passed / attempted checks with failures retained; do not count planned rows as attempted checks. The preparation itself supplies **zero new live observations**.
