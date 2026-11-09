# Charcha — final submission package

Updated 10 November 2026. The full application suites were checked on 9 November; the build and seven runtime checks were repeated successfully on 10 November. These materials are published for entry preparation; a social post and final form submission still require the owner.

## What to submit

The actual Microsoft submission form requires a **2–3 minute demo** and a project URL containing a solution-pitch document of **no more than one page**. The 60-second film serves the social post / short-demo category. The form marks the social link optional for bonus awards, while the public challenge page instructs entrants to post publicly; include it for this entry.

Actual fields, in order: full name; registered email; teammate's registered email (optional); higher-education institution; project URL containing the one-page pitch; 2–3 minute demo URL; LinkedIn/X post URL (optional field for bonus awards). No separate architecture essay field is present: put the technical explanation and evidence in the linked pitch.

The [official challenge page](https://www.gnani.ai/internship) states **10 November 2026, 11:59 PM IST** as the deadline. Use the submission form sent to the registered email.

1. Required form demo: [2:30 submission film](media/Charcha-2m30-submission-demo.mp4), 1080p with full decoding verified. Upload it to a viewable video host and enter that link. The [60-second social film](media/Charcha-60-second-social.mp4) is the short-demo cut, not a replacement for the form's longer video.
2. Project URL: [github.com/Jatin2567/Charcha](https://github.com/Jatin2567/Charcha), containing the [one-page pitch PDF](Charcha-one-page-pitch.pdf), source, architecture and evidence.
3. Each entrant's actual contribution and requested registration/eligibility details.
4. A public LinkedIn or X post published before submission. Tag Gnani AI and use `#GreatIndianAIInternshipChallenge` and `#GnaniAI`. Nominate one post link per platform used.

Check the repository, PDF and uploaded video while signed out before submitting. [Award positioning](AWARD_POSITIONING.md) maps all ten categories to the available evidence and eligibility conditions. The official rules allow at most one award per individual/team; no award or internship is guaranteed.

## Project form copy

**Title:** Charcha — Multilingual meetings with shared understanding

**Short description:** Charcha combines multilingual browser conversations, consented personal-voice interpretation, original and translated captions, corrections, individual acknowledgements and a bilingual recap.

**Problem and users:** Teams, students and community organisers may share a goal without sharing a fluent language. A changed time, count or room number can leave participants following different instructions. Charcha helps people hear an interpretation, review both texts, correct a message and acknowledge the updated version. Financial savings and reductions in misunderstandings have not been measured.

**Implementation:** LiveKit carries browser audio/video. Gnani Prisma recognises speech, hosted Evon translates it, and Gnani speech/voice-cloning APIs synthesize the listener's language. React/TypeScript and Python/FastAPI provide host admission, versioned captions, per-listener acknowledgements, exports and performance history. Modal supplies meeting-driven inference; GCP hosts the application. The full inference chain is not verified India-only.

**Gnani technology:** Prisma, Evon v3.3, Timbre and voice embeddings/cloned synthesis. The recording runner explicitly requested `prisma-v3.0`; adapter defaults are `timbre-v2.5` and `vachana-vc-v1`. The prepared Evon deployment uses `gnani/gnani-evon-v3.3-30B-A3B`. Defaults are not independent provider-returned version attestations.

**Demo evidence:** Saved Hindi→English provider output is replayed through the actual interface. A typed correction changes room three to room four. Automated test listener Alex separately acknowledges the corrected version; the bilingual recap retains both versions. This demonstrates the workflow, not human comprehension. The source voice is synthetic test speech, the personas are illustrated, and the video is edited. It is not a current live latency or multi-user load benchmark.

The recap scene also displays exact Tamil, Bengali and Telugu outputs from separate 31 October tests. Their date and separate-recording provenance are shown; they are not represented as translations from the workshop meeting.

**Recorded timing shown:** 3.94 s for the original turn and 4.23 s for the typed correction, from translation start to first decoded synthesis audio. These are two recorded cases from 9 November, excluding speech recognition, meeting transport and listener playback. VoiceShield is visibly labelled experimental.

**Limits:** Ten languages are configurable; measured quality coverage is narrower. Historical provider tests delivered nine of ten attempted routes across five languages, with meaning review pending. VoiceShield is experimental, without an established AI-voice detection rate. Acknowledgements and recap hashes are not identity checks, legal agreement or guaranteed translation accuracy.

**Contributions:** Enter actual participant name(s), roles and work. Disclose external models, libraries and AI-assisted development/design accurately. Do not invent a teammate or claim all work was unaided.

**App:** https://charcha-234398803946.asia-south2.run.app/

## Social post to accompany the video

One corrected room number can change everyone's plan.

I built चर्चा (Charcha) to help multilingual teams keep track of what was said, what changed, and who acknowledged the update. Built using Gnani Prisma, Evon and speech/voice-cloning APIs, it combines multilingual meetings, consented personal voices, original and translated captions, versioned corrections and bilingual PDF/WhatsApp recaps.

The engineering extends beyond the call screen: shared translation branches per target language, ordered playback, refresh/reconnect recovery, host admission, separate administrator MFA, saved performance reports and meeting-driven GPU lifecycle management. VoiceShield adds experimental audio-based screening with visible status.

The demo follows a workshop instruction from room three to room four, with a fresh acknowledgement and both versions retained in the recap. It uses recorded Hindi–English provider output, synthetic test speech, illustrated personas and labelled UI replay, alongside earlier Tamil, Bengali and Telugu excerpts. Development and presentation used AI assistance. This is a workflow demonstration, not a live latency or deepfake-accuracy benchmark.

Project and one-page pitch: https://github.com/Jatin2567/Charcha

#GreatIndianAIInternshipChallenge #GnaniAI #IndicAI #VoiceAI #WebRTC

When publishing, select Gnani AI's actual account in the tag selector and attach the MP4. This draft has not been posted. Host admission is required; the app link does not promise unattended judge access or active inference.

## Evidence and remaining actions

The [final submission review](FINAL_SUBMISSION_CHECK.md) records the package, public-file, layout, caption and claim checks.

Full local suites on 9 November: **1,468 backend tests passed, one skipped; 322 frontend tests and seven runtime checks passed; production build passed**. The build and seven runtime checks passed again on 10 November; the build retains an advisory for a bundle above 500 kB. The 9 November hosted checks returned 200 for the page and health endpoint and 401 for anonymous performance history. No fresh live interpretation test was performed for this release. Video files passed full decoding; hashes, duration and subtitle checks are recorded in the [media verification record](media/verification.json).

- [Media sources and editing disclosures](media/SOURCES_AND_NOTES.txt).
- [Submission-film captions](media/Charcha-2m30-captions.srt) and [social-film captions](media/Charcha-social-captions.srt).
- [Release notes](SUBMISSION_RELEASE_NOTES.md) and [actual commit history](https://github.com/Jatin2567/Charcha/commits/main/).
- Detailed local logs and provider receipts remain private; they are not published with account or billing information.
- Separate Hindi–Telugu/Punjabi human review remains unperformed: [rehearsal guide](LIVE_SUBMISSION_REHEARSAL.md).
- Owner still needs to publish the demo post, provide its URL, complete entrant details and submit the emailed form.

Do not upload the private work directory, .env, credentials, identity backups or billing records. Only reviewed source and sanitised evidence belong in the public repository. Repository publication does not post to social media or submit the challenge form.
