# Charcha — final submission package

Updated 9 November 2026. These are prepared materials, not a submitted entry. Public video/post links and entrant contributions still need the owner's completion.

## What to submit

**Correction after inspecting the actual Microsoft submission form:** the required demo field specifies **2–3 minutes**, and the required project URL must include a solution-pitch document of **no more than one page**. The existing 60-second film is for the social post / short-demo category; it does not by itself satisfy the longer form requirement. A 2–3 minute walkthrough is still to be prepared. The form marks the social link optional for bonus awards, while the public challenge page instructs entrants to post publicly; include it for this entry.

Actual fields, in order: full name; registered email; teammate's registered email (optional); higher-education institution; project URL containing the one-page pitch; 2–3 minute demo URL; LinkedIn/X post URL (optional field for bonus awards). No separate architecture essay field is present: put the technical explanation and evidence in the linked pitch. Copy-ready post and pitch text are in `work/submission-final/LINKEDIN_FINAL.txt` and `ONE_PAGE_PITCH.txt`.

The [official challenge page](https://www.gnani.ai/internship) states **10 November 2026, 11:59 PM IST** as the deadline. Use the submission form sent to the registered email.

1. Required form demo: a **2–3 minute** video link (pending). The existing `work/demo-video/story-v11/Charcha-60-second-final.mp4` is the verified 60-second social/short-demo cut, not a replacement for that field.
2. Written project explanation and Gnani technology details below.
3. Each entrant's actual contribution and requested registration/eligibility details.
4. A public LinkedIn or X post published before submission. Tag Gnani AI and use `#GreatIndianAIInternshipChallenge` and `#GnaniAI`. Nominate one post link per platform used.

A repository/app link is useful supporting evidence. The public rules do not explicitly require a public GitHub repository; follow additional fields in the actual form. This checkout has no Git remote configured. Do not assume local edits are published.

## Project form copy

**Title:** Charcha — Multilingual meetings with shared understanding

**Short description:** Charcha combines multilingual browser conversations, consented personal-voice interpretation, original and translated captions, corrections, individual acknowledgements and a bilingual recap.

**Problem and users:** Teams, students and community organisers may share a goal without sharing a fluent language. A changed time, count or room number can leave participants following different instructions. Charcha helps people hear an interpretation, review both texts, correct a message and acknowledge the updated version. Financial savings and reductions in misunderstandings have not been measured.

**Implementation:** LiveKit carries browser audio/video. Gnani Prisma recognises speech, hosted Evon translates it, and Gnani speech/voice-cloning APIs synthesize the listener's language. React/TypeScript and Python/FastAPI provide host admission, versioned captions, per-listener acknowledgements, exports and performance history. Modal supplies meeting-driven inference; GCP hosts the application. The full inference chain is not verified India-only.

**Gnani technology:** Prisma, Evon v3.3, Timbre and voice embeddings/cloned synthesis. The recording runner explicitly requested `prisma-v3.0`; adapter defaults are `timbre-v2.5` and `vachana-vc-v1`. The prepared Evon deployment uses `gnani/gnani-evon-v3.3-30B-A3B`. Defaults are not independent provider-returned version attestations.

**Demo evidence:** Saved Hindi→English provider output is replayed through the actual interface. A typed correction changes room three to room four. Automated test listener Alex separately acknowledges the corrected version; the bilingual recap retains both versions. This demonstrates the workflow, not human comprehension. The source voice is synthetic test speech, the personas are illustrated, and the video is edited. It is not a current live latency or multi-user load benchmark.

The recap scene also displays exact Tamil, Bengali and Telugu outputs from separate 31 October tests. Their date and pending meaning review are shown; they are not represented as translations from the workshop meeting.

**Recorded timing shown:** 3.94 s for the original turn and 4.23 s for the typed correction, from translation start to first decoded synthesis audio. These are two recorded cases from 9 November, excluding speech recognition, meeting transport and listener playback. VoiceShield is visibly labelled experimental.

**Limits:** Ten languages are configurable; measured quality coverage is narrower. Historical provider tests delivered nine of ten attempted routes across five languages, with meaning review pending. VoiceShield is experimental, without an established AI-voice detection rate. Acknowledgements and recap hashes are not identity checks, legal agreement or guaranteed translation accuracy.

**Contributions:** Enter actual participant name(s), roles and work. Disclose external models, libraries and AI-assisted development/design accurately. Do not invent a teammate or claim all work was unaided.

**App:** https://charcha-234398803946.asia-south2.run.app/

## Social post to accompany the video

I built Charcha for the Great Indian AI Internship Challenge: multilingual meetings where a changed message gets a fresh acknowledgement.

The demo follows a workshop instruction from room three to room four. It shows recorded Hindi-to-English output, the actual correction and confirmation interface, and a bilingual recap that keeps both versions.

Charcha uses Gnani Prisma, Evon and Gnani voice synthesis/cloning, with LiveKit, Modal and Google Cloud. The presentation uses fictional test personas, recorded synthetic test speech, AI-assisted artwork/narration and labelled UI replay. It is a workflow demonstration, not a live latency or deepfake-accuracy benchmark.

Built using Gnani AI. App: https://charcha-234398803946.asia-south2.run.app/

#GreatIndianAIInternshipChallenge #GnaniAI

When publishing, select Gnani AI's actual account in the tag selector and attach the MP4. This draft has not been posted. Host admission is required; the app link does not promise unattended judge access or active inference.

## Evidence and remaining actions

Final checks on 9 November: **1,468 backend tests passed, one skipped; 322 frontend tests and seven runtime checks passed; production build passed**. The hosted page and health endpoint returned 200; anonymous performance history returned 401. Initial restricted-Windows test attempts were superseded by successful runs. No fresh live interpretation test was performed. The 60-second video passed full decoding and its saved SHA-256 matched. A limited pattern check of 453 publishable text files found no matches for the selected credential patterns; this is not a full security audit or history scan.

- Video disclosures: `work/demo-video/story-v11/SOURCES_AND_NOTES.txt`.
- Video duration, decode check and SHA-256: `work/demo-video/story-v11/verification.json`.
- Final local check logs: `work/submission-final/`.
- Provider receipts: `work/demo-video/live-evidence-2/`, private and ignored by Git.
- Separate Hindi–Telugu/Punjabi human review remains unperformed: [rehearsal guide](LIVE_SUBMISSION_REHEARSAL.md).
- Owner still needs to publish the demo post, provide its URL, complete entrant details and submit the emailed form.

Do not upload the private work directory, .env, credentials, identity backups or billing records. Publish reviewed source and sanitised evidence only. No social post, repository publication or final form submission was performed by this preparation step.
