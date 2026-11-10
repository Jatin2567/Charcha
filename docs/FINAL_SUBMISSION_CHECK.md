# Final submission review

Updated 10 November 2026. **This source revision includes the refreshed films, one-page pitch, approved feedback and reviewer workflow with scoped reporting.** Local media/packaging checks passed. Release `reviewer-reporting-20261110`, from tested code commit `d0091916cc29c3a1cd1a4375d5db9fbc4c9f340e`, was deployed and its health/access checks verified. Source publication, public video/social links and form submission remain distinct actions; deployment did not issue reviewer invitations or exercise a live provider flow.

| Check | Result and scope |
| --- | --- |
| Actual form requirements | Saved form definition requires a 2–3 minute video and a project URL containing a pitch of at most one page. Field order and optional teammate/social fields match the submission guide. |
| Required film | 160.0 seconds (2:40), 1920 × 1080; final full decode passed; 24 subtitle cues are ordered and non-overlapping. |
| Social film | 60.0 seconds, 1920 × 1080; final full decode passed; 11 subtitle cues are ordered and non-overlapping. |
| Pitch and feedback | One-page A4 pitch rendered and visually reviewed. The public-copy hash matches the verified PDF. Sathvika's full approved review is included, retaining her latency observation; exact text was checked after PDF extraction. |
| Final pitch refresh | Clearer three-language story and workflow, Gnani architecture, 10 November application checks and dated 9 November partial timings. Visible headline and metadata agree; repository/app hyperlinks checked; independent claim and layout review passed. |
| Social-post link | Entrant supplied https://lnkd.in/p/g5rqTQaZ; saved in the kit; the form draft is tracked separately. Automated lookup did not expose the post content, so public visibility, company mentions and hashtags are not independently verified. |
| Portal views | Captured Home, Prejoin, Performance, Voice Studio, Test lab and Audio lab, plus meeting/recap. Final encoded frames reviewed for layout and evidence labels. |
| Music and speech | Original instrumental music with speech ducking and extra attenuation during language examples. Natural-speed speech is preserved; final caption timing follows the edit and encoded peaks stay below 0 dBFS. No new provider calls. Human listening preference remains subjective. |
| Source publication | This revision contains the intended source, media and pitch. Verify its commit and asset URLs on the public repository after push; a source release does not deploy the application. |
| Download package | Package assembled from reviewed assets, including full participant feedback and reviewer guide; ZIP CRC and every packaged hash verified. |
| Documentation links | New filenames and relative targets checked after media/PDF placement. |
| Claims | Test counts, recorded model settings and route-delivery counts match saved evidence. Timings are labelled as partial server stages; edited/synthetic material and experimental VoiceShield are disclosed. |
| Repository presentation | Product/setup/architecture copy separates implementation from measured provider quality. This revision adds reviewer invitation/resource controls and bounded pre-meeting preparation; the matching web/API release was deployed on 10 November. |
| Reporting-release application checks, 10 Nov 2026 | **1,579 backend tests passed, one skipped, in 224.65 s; 335 frontend tests passed across 47 files; seven runtime checks and production build passed.** The final eight-test reporting run overlaps seven full-suite cases and includes an uppercase-code case added after full-suite collection; do not sum the results. Desktop/mobile and scoped-report walkthroughs passed against the actual local API with providers mocked and zero provider calls. See the [source-release record](REVIEWER_RELEASE_VERIFICATION.json). |
| Final hosted reporting release, 10 Nov 2026 | Health/access check at 16:31:03 UTC: health 200; new Reviewer, Prejoin, Usage and Performance components; identity configured; anonymous protected endpoints, including usage/account engine, returned 401. At 16:31:12 UTC all 43 source-file hashes matched tested code, with no missing or extra files. No real reviewer invitations issued, authenticated live provider flow or Gnani/Modal calls. |
| Earlier reviewer-preparation release, 10 Nov 2026 | Historical result: 1,558 backend passed, one skipped (194.81 s); 328 frontend across 47 files; seven runtime checks/build passed. Separate generator checks: 40 passed, two platform skips. The earlier 16:01:36 UTC rollout checked 13 source hashes. These are not the final reporting-release counts. |
| Historical application evidence | Full suites on 9 November: 1,468 backend tests passed, one skipped; 322 frontend tests and seven runtime checks passed. The earlier 10 November media pass repeated the build, seven runtime checks and the offline three-account rehearsal. These historical counts do not describe the later reviewer changes. |
| New provider usage | No new Gnani requests or Modal sessions for the music/portal refresh. Previously approved Telugu/Punjabi standard-voice readings are reused. |

This is a submission-material review. It does not certify live multi-user translation accuracy, full speech-end-to-listener latency, VoiceShield detection accuracy or production capacity. The existing build has a non-blocking advisory for a JavaScript bundle above 500 kB.

## Owner's remaining submission steps

1. Verify that the intended source revision, refreshed reviewed assets and pitch are visible on the public repository.
2. Upload the [2:40 build film](media/Charcha-2m40-multilingual-build.mp4) to a video host and check that its viewing link works while signed out.
3. Use **https://github.com/Jatin2567/Charcha** for the project field after checking the [refreshed one-page pitch](Charcha-one-page-pitch.pdf) while signed out.
4. Check the [entrant-supplied social post](https://lnkd.in/p/g5rqTQaZ) is public and includes the actual Gnani company mention and both required hashtags.
5. Review the confirmed entrant details and saved post link in the form draft; add the build video's viewing link and submit the official form. No submission or receipt is claimed by this review.

See the [submission guide](SUBMISSION.md), [award evidence map](AWARD_POSITIONING.md), [media verification](media/verification.json) and [sources/editing notes](media/SOURCES_AND_NOTES.txt). No form or social post was submitted by this review.
