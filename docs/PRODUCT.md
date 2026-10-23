# Product and page specification

Artha-Mesh Track B is an audio meeting application for people who prefer different Indian languages. Its primary journey is **start a room → choose a language → invite someone → speak → hear interpretation → review and confirm meaning**.

## Design direction

Familiar meeting controls inspired by conferencing conventions: visible microphone state, speaker playback state, participant identity, clear leave action, device check before joining, and a dedicated transcript panel. The visual identity is original: warm off-white workspaces, dark meeting stage, emerald actions, restrained saffron details, typographic language symbols, and a mesh mark. The product does not reproduce another company's branding.

Labels describe what the product actually does. Demo rooms say they are scripted. Device voices, if used in a demo, are identified as browser speech synthesis. Configured credentials do not imply a successful provider connection. Server processing time is not presented as measured listener playback delay.

## Pages and responsibilities

| Page           | Primary task                            | State and behavior                                                                                                                                                      |
| -------------- | --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Home           | Start or join a conversation            | Meeting title, invitation code/link, language preview, explicit demonstration entry, recent saved sessions                                                              |
| Prejoin        | Decide how to participate               | Display name, listening/speaking language, microphone/device checks, voice choice, explicit consent; no capture on home                                                 |
| Meeting        | Converse                                | Participant cards, active speaker, captions/transcript, source and translated text, per-turn confirmation, microphone/speaker controls, invite copy, room details, exit |
| Recap          | Review conversation                     | Translation history, confirmed turns, download, explicit save to this browser, delete                                                                                   |
| Voice studio   | Enroll a voice intentionally            | Consent, clean 5–30-second spoken recording, playback, upload to membership-scoped server, deletion, stock voice fallback                                               |
| Settings/setup | Understand and configure the experience | Device selection, default language, local preferences, provider setup status, live/demo distinction                                                                     |

## Important interaction details

- A participant language means the source transcription language and preferred output language. Code-mixed content remains an evaluation concern, not automatic unrestricted language detection.
- Every original speaker's stream is transcribed once. The server translates and synthesizes once per unique listener language. Same-language listeners receive an agent-forwarded original PCM stream.
- Source audio is routed to the translation participant. Other users hear the appropriate translated/forwarded agent track. Original and translated audio are not both played.
- Translated audio is never transcribed again. A participant does not hear the interpretation of their own speech.
- Source segment order is preserved. Backpressure and failures are visible; the system must not silently build an unlimited audio queue.
- User confirmation means they acknowledge a turn's meaning. It is not an order, payment authorization, or claim that a transcript is correct.
- A typed utterance is an explicit alternative input; it is never presented as a microphone transcription.
- Browser permission, unsupported output-device selection, provider failure, missing configuration, and autoplay blocking must have understandable recovery messages.

## Data boundaries

Room membership is protected by a room-scoped expiring token. An invitation code grants the ability to request membership; this prototype does not include organisation SSO or host admission. Keep invitations private. Voice embeddings remain server-side and tied to membership. Raw reference audio is processed in memory rather than stored by this application. Upstream provider retention is a separate policy.

The single-process server keeps active room state in memory and expires it. Explicitly saved recaps remain in the user's current browser until deleted. The browser must not put membership tokens or voice references in persistent history.

## Scope

Included: Hindi, Tamil, Bengali and English selection; one-way, bidirectional and multi-party routing; configurable real providers; streaming transcription and speech synthesis; optional voice cloning; transcripts and confirmation; diagnostics; reproducible evaluation tools.

Excluded: Track A spoof detection, fraud verdicts, PSTN/SIP calling, regulated identity verification, guaranteed translation accuracy, guaranteed latency, verified nationwide data residency, billing, and multi-replica durable room orchestration.

## Acceptance journey

1. Enter the clearly labelled scripted demo without credentials.
2. Join with a chosen name and language; inspect participant and transcript states.
3. Run the example conversation, change transcript views, and confirm a turn.
4. Toggle audio controls, copy an invitation, leave, download and explicitly save a recap.
5. Start the backend in demo mode and repeat against real HTTP/WebSocket room state.
6. Configure the live environment; join from two browsers, speak both directions, and verify target-only audio.
7. Add a third language, enroll a consented voice, verify fan-out, and measure actual output quality and delay.

Steps 6–7 require working provider accounts/compute and microphone access. A passing scripted demo cannot verify those live properties.
