# Product and page specification

Charcha Track B is an audio/video meeting application for people who prefer different languages. Its primary journey is **host signs in → starts a room → invites and admits participants → participants choose a language → speak → hear interpretation → review and acknowledge the current message**. This specification reflects the application on 10 November 2026; deployed settings and measurement boundaries are recorded in [the operating guide](ON_DEMAND_MEETINGS.md).

## Design direction

Familiar meeting controls inspired by conferencing conventions: visible microphone state, speaker playback state, participant identity, clear leave action, device check before joining, and a dedicated transcript panel. The visual identity uses light workspaces, a charcoal meeting stage, royal-blue actions, restrained warm accents and a waveform mark. The product does not reproduce another company's branding.

Labels describe what the product actually does. Demo rooms say they are scripted. Device voices, if used in a demo, are identified as browser speech synthesis. Configured credentials do not imply a successful provider connection. Server processing time is not presented as measured listener playback delay.

## Pages and responsibilities

| Page           | Primary task                            | State and behavior                                                                                                                                                      |
| -------------- | --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Home           | Start or join a conversation            | Meeting title, invitation code/link, language preview, explicit demonstration entry, recent saved sessions                                                              |
| Prejoin        | Decide how to participate               | Display name, listening/speaking language, microphone/device checks and explicit processing consent; no capture on home                                                  |
| Meeting        | Converse                                | Participant cards, active speaker, captions/transcript, source and translated text, per-turn confirmation, microphone/speaker controls, invite copy, room details, exit |
| Recap          | Review conversation                     | Translation history, confirmed turns, download, explicit save to this browser, delete                                                                                   |
| Voice studio   | Enroll a voice intentionally            | Consent, clean 5–30-second spoken recording, playback, membership-scoped enrollment and deletion; required-voice rooms mute the speaker after deletion                      |
| Settings/setup | Understand and configure the experience | Device selection, default language, local preferences, provider setup status, live/demo distinction                                                                     |

## Important interaction details

- A participant language means the source transcription language and preferred output language. Code-mixed content remains an evaluation concern, not automatic unrestricted language detection.
- An active original speaker's stream is transcribed once when a different-language listener is present. The server translates and synthesizes once per unique target listener language. Same-language listeners receive an agent-forwarded original PCM stream without recognition or synthesis when they are the only audience.
- Source audio is routed to the translation participant. Other users hear the appropriate translated/forwarded agent track. Original and translated audio are not both played.
- Translated audio is never transcribed again. A participant does not hear the interpretation of their own speech.
- Source segment order is preserved. Backpressure and failures are visible; the system must not silently build an unlimited audio queue.
- User confirmation means they acknowledge a turn's meaning. It is not an order, payment authorization, or claim that a transcript is correct.
- A typed utterance is an explicit alternative input; it is never presented as a microphone transcription.
- Browser permission, unsupported output-device selection, provider failure, missing configuration, and autoplay blocking must have understandable recovery messages.

## Data boundaries

Configured deployments authenticate accounts and restrict meeting creation to the designated host. Guests request entry, and the host admits or denies them. The separate administrator account requires additional authenticator verification. A room invitation is a way to request entry, not permission to bypass admission. Room membership uses a scoped expiring token; reconnecting an admitted seat requests a fresh media credential without extending membership. Voice embeddings remain server-side and tied to membership. Raw reference audio is processed in memory rather than stored by this application. Upstream provider retention is a separate policy.

The single-process server keeps active room state in memory and expires it. Explicitly saved recaps remain in the user's current browser until deleted. The browser must not put membership tokens or voice references in persistent recap history. Technical performance reports have separate account-scoped server persistence; pending writes and interrupted meetings are labelled explicitly.

## Scope

Included: ten configurable language choices (Hindi, Tamil, Bengali, English, Telugu, Kannada, Malayalam, Marathi, Gujarati and Punjabi); one-way, bidirectional and multi-party routing; configurable real providers; streaming transcription, speech synthesis and consented personal-voice enrollment; versioned corrections and per-listener acknowledgements; bilingual recap exports; diagnostics and reproducible offline evaluation plans. Hosted interpreted rooms require enrollment before speaking, while listening does not require enrollment. Standard synthesis remains available for separately configured tests. VoiceShield provides optional experimental source-audio screening, not a verified fraud verdict. Ten language choices and ninety designed directions do not establish completed real-provider or human-listening acceptance.

Excluded: validated fraud or identity verdicts, PSTN/SIP calling, regulated identity verification, guaranteed translation accuracy, guaranteed latency, verified nationwide data residency, authoritative provider billing, and multi-replica durable room orchestration.

## Acceptance journey

1. Enter the clearly labelled scripted demo without credentials.
2. Join with a chosen name and language; inspect participant and transcript states.
3. Run the example conversation, change transcript views, and confirm a turn.
4. Toggle audio controls, copy an invitation, leave, download and explicitly save a recap.
5. Start the backend in demo mode and repeat against real HTTP/WebSocket room state.
6. Configure an authorized live environment, sign in, complete host admission and enroll each consenting speaker if required by the room. Join from two browsers, speak both directions, and verify target-only audio.
7. Add a third language, verify fan-out and independently review meaning, intelligibility and delay for each direction. Use standard voices only in a test configuration that permits them.
8. Evaluate cloned output with the consenting speaker and a fluent listener. Delete the profile and verify that required-voice rooms prevent further speech until enrollment is repeated.

Steps 6–8 require working provider accounts/compute and microphone access. A passing scripted demo cannot verify those live properties.
