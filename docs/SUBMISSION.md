# Charcha — final submission package

Updated 10 November 2026. This source revision includes the 2:40 build film, 60-second multilingual story, refreshed one-page pitch, approved participant feedback and reviewer setup guide. Media and packaging have been checked locally. The matching reviewer web/API release was deployed and its health, served components and access restrictions checked on 10 November; no authenticated live provider flow was run. Source publication, video/social publication and challenge submission are separate actions. Dated evidence is listed below.

## What to submit

The actual Microsoft submission form requires a **2–3 minute demo** and a project URL containing a solution-pitch document of **no more than one page**. The 60-second film serves the social post / short-demo category. The form marks the social link optional for bonus awards, while the public challenge page instructs entrants to post publicly; include it for this entry.

Actual fields, in order: full name; registered email; teammate's registered email (optional); higher-education institution; project URL containing the one-page pitch; 2–3 minute demo URL; LinkedIn/X post URL (optional field for bonus awards). No separate architecture essay field is present: put the technical explanation and evidence in the linked pitch.

The [official challenge page](https://www.gnani.ai/internship) states **10 November 2026, 11:59 PM IST** as the deadline. Use the submission form sent to the registered email.

1. Required form demo: [2:40 build film](media/Charcha-2m40-multilingual-build.mp4). The final render and full decode passed. Upload it to a viewable video host and enter its watch link. The [60-second multilingual film](media/Charcha-60s-voice-cloning-social.mp4) is the social cut, not a replacement for the form's longer video.
2. Project URL: [github.com/Jatin2567/Charcha](https://github.com/Jatin2567/Charcha). This revision contains source, architecture, the [refreshed one-page pitch](Charcha-one-page-pitch.pdf) and reviewed media. Verify these exact files are visible at the submitted public revision.
3. Each entrant's actual contribution and requested registration/eligibility details.
4. Entrant-supplied [LinkedIn post](https://lnkd.in/p/g5rqTQaZ), supplied on 10 November. Automated lookup could not read the short-link destination, so public visibility, the actual Gnani company mention and `#GreatIndianAIInternshipChallenge` / `#GnaniAI` still need a final owner check. The post was not published by this preparation.

Check the repository, PDF and uploaded video while signed out before submitting. [Award positioning](AWARD_POSITIONING.md) maps all ten categories to the available evidence and eligibility conditions. The official rules allow at most one award per individual/team; no award or internship is guaranteed.

## Project form copy

**Title:** Charcha — Multilingual meetings with shared understanding

**Short description:** Charcha combines multilingual browser conversations, consented personal-voice interpretation, original and translated captions, corrections, individual acknowledgements and a bilingual recap.

**Problem and users:** Teams, students and community organisers may share a goal without sharing a fluent language. A changed time, count or room number can leave participants following different instructions. Charcha helps people hear an interpretation, review both texts, correct a message and acknowledge the updated version. Financial savings and reductions in misunderstandings have not been measured.

**Implementation:** LiveKit carries browser audio/video. Gnani Prisma recognises speech, hosted Evon translates it, and Gnani speech/voice-cloning APIs synthesize the listener's language. React/TypeScript and Python/FastAPI provide host admission, versioned captions, per-listener acknowledgements, exports and performance history. Modal supplies meeting-driven inference; GCP hosts the application. The full inference chain is not verified India-only.

**Gnani technology:** Prisma, Evon v3.3, Timbre and voice embeddings/cloned synthesis. The recording runner explicitly requested `prisma-v3.0`; adapter defaults are `timbre-v2.5` and `vachana-vc-v1`. The prepared Evon deployment uses `gnani/gnani-evon-v3.3-30B-A3B`. Defaults are not independent provider-returned version attestations.

**Demo evidence:** Fictional Asha, Ravi and Meher represent Hindi, Telugu and Punjabi participants. Actual app screens from a scripted three-account rehearsal show a room-three-to-room-four correction, individual acknowledgements of the new version and a bilingual recap. Both films include a saved synthetic Hindi reference and its English cloned-synthesis output, plus separately prepared Telugu/Punjabi standard-voice readings. The clone demonstrates the embedding/synthesis path with a synthetic reference, not a real participant or validated human likeness. This is not a new live three-device interpretation test.

**Presentation refresh:** Original local music is lowered under speech, with a more energetic 120 BPM story arrangement and a quieter engineering section. The portal walkthrough includes Home, Prejoin, Performance, Voice Studio, Test lab and Audio lab alongside the meeting and recap. These offline views show implemented product surfaces; they do not imply active provider services, real-time readings or successful deepfake detection. Final coverage and media checks are recorded in the [verification record](media/verification.json).

**Recorded timing shown:** 3.94 s for an original turn and 4.23 s for a typed correction, from translation start to first decoded synthesis audio. These are separate saved Hindi→English cases from 9 November, excluding speech recognition, meeting transport and listener playback. They are not measurements of the Hindi/Telugu/Punjabi rehearsal. VoiceShield remains experimental.

**Limits:** Ten languages are configurable; measured quality coverage is narrower. Historical provider tests delivered nine of ten attempted routes across five languages, with meaning review pending. VoiceShield is experimental, without an established AI-voice detection rate. Acknowledgements and recap hashes are not identity checks, legal agreement or guaranteed translation accuracy.

**Contributions:** Enter actual participant name(s), roles and work. Disclose external models, libraries and AI-assisted development/design accurately. Do not invent a teammate or claim all work was unaided.

**App:** https://charcha-234398803946.asia-south2.run.app/

## Approved participant feedback

> The platform provides a really useful way to communicate with people who speak different languages through both text and voice translation. I liked how it makes conversations more accessible and helps people understand each other better. The experience was engaging and easy to follow, although there is some scope to improve response latency. Overall, it's a useful platform that can help people connect without language barriers.

**Sathvika — tech student and Telugu speaker.** Publication approved; only sentence spacing has been corrected. This is personal product feedback, not a controlled language-accuracy evaluation or a latency measurement. Her observation about response latency is retained in full. The same review is included in the one-page pitch and submission kit.

For hands-on evaluation, the [reviewer guide](REVIEWER_GUIDE.md) explains verified `@gnani.ai` automatic meeting-host access, administrator approval for other verified accounts, optional private invitations, reviewer-owned resources and explicit pre-meeting translation preparation. Domain access identifies a verified company email, not an appointed judge. It never grants administrator access or starts provider usage by itself. Personal providers still depend on running Charcha identity, application and meeting-media services. See the guide's access-update record for deployment verification; the 10 November invitation-only results below remain historical.

## Social post to accompany the video

“Room four, not room three.”

One small correction. Three languages. Everyone needs the same update.

I built चर्चा (Charcha) for teams who share a goal without sharing a fluent language.

The story follows Asha, Ravi and Meher through Hindi, Telugu and Punjabi. Charcha helps them review both texts, correct the message, acknowledge the updated version individually and keep a bilingual recap.

At its core: @gnani.ai Prisma for speech recognition, Evon for translation and Timbre for speech synthesis. Behind the interface: shared translation branches, ordered playback, reconnect recovery, host admission, meeting-driven GPU lifecycle, saved performance reports, consented voice cloning and experimental VoiceShield audio screening.

Built for The Great Indian AI Internship Challenge, with AI-assisted development and demo production. The film uses fictional personas, actual app screens from a scripted three-account rehearsal and prepared speech. The build film explains the architecture and separately recorded performance evidence.

Where have language differences made a simple instruction harder to follow? I’d value feedback from multilingual teams and voice-AI builders.

Code and engineering notes: https://github.com/Jatin2567/Charcha

#GreatIndianAIInternshipChallenge #GnaniAI #IndicAI #VoiceAI #WebRTC

When publishing, select Gnani AI's actual account in the tag selector and attach the MP4. This draft has not been posted. Host admission is required; the app link does not promise unattended judge access or active inference.

## Evidence and remaining actions

The [submission review](FINAL_SUBMISSION_CHECK.md) separates this source revision's local checks from hosted operation and lists the remaining publication and submission steps.

The final **10 November reporting-release checks passed: 1,579 backend tests, one skipped; 335 frontend tests across 47 files; seven runtime checks; production build**. The backend run took 224.65 seconds. Eight focused reporting tests also passed: seven overlap the full suite, and one uppercase-code case was added after full-suite collection, so these results must not be summed. Desktop/mobile and scoped-report walkthroughs passed against the actual local API with mocked providers and zero provider calls. The earlier generator check remains a separate historical result: 40 passed with two platform skips. These checks establish application behavior, not live provider accuracy, availability or speed. The refreshed one-page pitch cites these 10 November checks alongside explicitly dated 9 November partial latency cases. The films retain their 9 November evidence. The [source-release verification record](REVIEWER_RELEASE_VERIFICATION.json) keeps these results separate from media evidence.

Release **`reviewer-reporting-20261110`**, from tested code commit `d0091916cc29c3a1cd1a4375d5db9fbc4c9f340e`, passed hosted checks at **10 November 2026, 16:31:03 UTC**: health 200; new Reviewer/Prejoin/Usage/Performance components; configured identity; anonymous protected endpoints, including usage and account engine, denied with 401. At **16:31:12 UTC**, all 43 deployed source-file hashes matched, with no extra or missing files. This verified deployment and access boundaries; it issued no real invitations and made no Gnani/Modal calls. An authenticated live speech/GPU evaluation remains a separate step. The earlier 16:01 rollout and its 13-file check are retained as historical evidence in the release record.

Historical local suites on 9 November: **1,468 backend tests passed, one skipped; 322 frontend tests and seven runtime checks passed; production build passed**. The earlier 10 November media pass repeated the build, seven runtime checks and an offline three-account rehearsal. These are dated results; current reviewer-release checks belong in the [final review](FINAL_SUBMISSION_CHECK.md). The 9 November hosted checks returned 200 for the page and health endpoint and 401 for anonymous performance history. They are not a current hosted-health check. No fresh live interpretation test was performed for this revision. Media duration, decode, captions and integrity results refer to the exact files in the [media verification record](media/verification.json).

- [Media sources and editing disclosures](media/SOURCES_AND_NOTES.txt).
- [Build-film captions](media/Charcha-build-captions.srt) and [social-film captions](media/Charcha-social-captions.srt).
- [Release notes](SUBMISSION_RELEASE_NOTES.md) and [actual commit history](https://github.com/Jatin2567/Charcha/commits/main/).
- Detailed local logs and provider receipts remain private; they are not published with account or billing information.
- Separate Hindi–Telugu/Punjabi human review remains unperformed: [rehearsal guide](LIVE_SUBMISSION_REHEARSAL.md).
- Latest music/portal edits use no new Gnani or Modal calls. Earlier Telugu and Punjabi readings consumed their separate approved two-request grant; they are reused here.
- Verify the submitted public source revision and pitch, upload the build film and check its viewing URL, review the entrant-supplied social post, then review and submit the emailed form. Entrant details and the social link have been supplied; no form submission or receipt is claimed.

Do not upload the private work directory, .env, credentials, identity backups or billing records. Only reviewed source and sanitised evidence belong in the public repository. Repository publication does not post to social media or submit the challenge form.
