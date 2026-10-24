# Provider credit controls

The application enforces conservative daily usage reservations before live Gnani or Evon requests. The **Usage & limits** page reads `/api/usage` without probing any provider. Demo mode makes no paid provider calls and does not create a usage database.

These are application safeguards, not a provider balance, rupee estimate, or guarantee of the bill. Provider billing may use different units, rounding, minimum connection charges, tokens, or partial-request rules. Usage from other applications is outside this ledger. Set spending/quota controls in the Gnani, LiveKit and hosted Evon accounts as well. A self-hosted Evon GPU can cost money while idle; this application does not stop that machine.

## Conservative defaults

All counters are global across rooms and users of the API, shared for each UTC date. They reset at **00:00 UTC (05:30 IST)**. Restarting the server keeps the current day's usage.

| Environment setting                        | Default | What is reserved                                                                                                          |
| ------------------------------------------ | ------: | ------------------------------------------------------------------------------------------------------------------------- |
| `USAGE_STT_SECONDS_PER_DAY`                |     600 | One second before opening STT, then each further connected second in advance; includes handshake and idle microphone time |
| `USAGE_STT_CONNECTIONS_PER_DAY`            |      30 | Every upstream STT connection attempt, including reconnects and failed authentication                                     |
| `USAGE_MT_REQUESTS_PER_DAY`                |     100 | One attempt per translated target language                                                                                |
| `USAGE_MT_CHARACTERS_PER_DAY`              |  30,000 | Unicode source characters for each translated target language                                                             |
| `USAGE_TTS_REQUESTS_PER_DAY`               |     100 | One synthesis attempt per target language, standard or cloned                                                             |
| `USAGE_TTS_CHARACTERS_PER_DAY`             |  30,000 | Unicode input characters for each synthesis attempt                                                                       |
| `USAGE_VOICE_ENROLLMENTS_PER_DAY`          |       3 | Every voice embedding enrollment attempt                                                                                  |
| `USAGE_MAX_CONCURRENT_STT`                 |       3 | Maximum active STT adapter operations in one API worker                                                                   |
| `USAGE_MAX_CONCURRENT_OPERATIONS`          |       2 | Shared active MT, TTS and enrollment operations in one API worker                                                         |
| `USAGE_MAX_QUEUED_OPERATIONS`              |      16 | Maximum waiting MT/TTS/enrollment admissions                                                                              |
| `USAGE_PROVIDER_ADMISSION_TIMEOUT_SECONDS` |       5 | Admission wait before a queued operation is rejected; no provider call or reservation occurs while waiting                |
| `USAGE_STT_MAX_RETRIES`                    |       3 | Automatic reconnects after consecutive transient STT failures; initial attempt plus up to three retries                   |
| `USAGE_MAX_LIVE_ROOM_SECONDS`              |     900 | Maximum live room lifetime from room creation, further limited by `ROOM_TTL_SECONDS`                                      |

`600` STT seconds means a total across simultaneous streams: three unmuted speakers can use 600 connected seconds in about 200 elapsed seconds. Silence on an unmuted microphone still counts. The defaults are development limits, not a representation of your Gnani plan. Adjust downward or upward only after checking your provider allowance. Set any daily resource limit to `0` to block that feature. Negative/unbounded limits are rejected. Change settings in `server/.env` (local development) or `.env` (Compose) and restart the API. Browsers cannot edit or reset budgets.

## Efficiency and stop behavior

- One STT stream is used per original speaker only when another active human listener needs a different language. An unmuted speaker alone, or in a room whose listeners all share the source language, opens no recognizer. Mute, membership expiry or the last different-language listener leaving closes ongoing STT within the 250 ms eligibility polling interval, plus socket shutdown time. Same-language audio remains forwarded without MT or synthesized speech. Such same-language-only conversations have no generated live captions/transcript; this tradeoff avoids spending recognition credits where no interpretation is needed.
- One MT/TTS branch is shared by all listeners who chose the same target language. Source audio is forwarded for same-language microphone listeners. Typed fallback bypasses MT when the requested target equals the source language, but still synthesizes speech.
- The daily connection cap and limited reconnect policy stop repeated connection failures from burning an unlimited number of attempts. Authentication, permission, payment and quota denials stop automatic STT retries. A stopped recognizer needs an explicit microphone restart after the underlying issue is resolved. Manual restarts remain subject to the same persistent caps.
- MT, TTS and enrollment have no automatic paid-request retries. A failed or cancelled operation keeps its reserved units because the application cannot know whether a provider billed a partial request. Synthesis never silently falls back to another paid voice request.
- The shared operation queue is bounded and waits at most five seconds by default. Reservations occur only after admission. This queue lets simultaneous target languages share the vendor slots; it is not an upstream retry mechanism. Stage latency includes admission waiting.
- Voice references are reused during their consenting membership. Translation and audio are not cached across people or conversations. Live inference results are not reused as a cross-user credit optimization.
- Live room/member access ends after at most 15 minutes by default. Existing rooms are swept every 30 seconds; the server requests removal of human LiveKit participants and disconnects its interpreter. Provider/network outages can delay or prevent that remote removal. Token expiry also prevents new joins after the room's lifetime, but token expiry alone does not disconnect an already connected participant. LiveKit account limits remain necessary.

## Persistent ledger and failures

Local development defaults to `server/data/usage.sqlite3`. `USAGE_DB_PATH` can select another persistent local path. The SQLite ledger has only UTC date, resource key and integer reserved units. It contains no transcript, names, audio, embeddings, model values, URLs, tokens or API keys. The directory and SQLite files are ignored by source control and excluded from the source archive.

All units required for a request are reserved in one SQLite transaction before contacting the provider. Concurrent reservations cannot cross the same daily cap. The application deliberately does not refund attempted requests. Existing in-flight requests can finish after their reservation; STT initiates close when the next second cannot be reserved. Connection close/transport delays and provider billing granularity mean this is not an exact billed-seconds cap.

If storage cannot be created, read or written, is corrupt, or is configured as an in-memory database, live provider calls **fail closed**. The UI shows unknown usage and unavailable storage. Restore the persistent path/permissions and restart the API. Do not delete or replace the file to clear usage: doing so removes the application's accounting history. Do not scale this local ledger over separate non-shared paths.

Compose mounts `usage-ledger` at `/app/data` and sets `USAGE_DB_PATH=/app/data/usage.sqlite3`; the image creates that directory for the non-root API user. Ordinary restarts and container replacements keep the named volume. Removing the volume loses accounting. A host bind mount must be writable by container UID `10001`. Docker/GPU deployment remains subject to validation on the intended host.

## Reading the page

The page shows reserved units, configured daily limits, remaining units, 80% warnings and exhausted resources. An unavailable ledger shows unknown counters. The provider balance is always labelled unavailable because no account-balance API has been connected. Configured caps remain visible in demo mode, with zero reserved usage. It never invents a wallet balance or monetary savings.

Local mocked tests cover atomic reservations, simultaneous callers, restart persistence, UTC rollover, zero limits, admission rejection, unavailable storage, adapter guards, idle STT budget termination and provider-error classification. They consume no real provider credits. Live billing reconciliation still needs the provider account's usage report.
