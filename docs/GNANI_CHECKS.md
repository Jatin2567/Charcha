# Gnani checks before deployment

Public hosting can wait. The prepared speech test calls Gnani directly from the local Python process; it needs neither a remote server nor LiveKit/Evon. It does **not** verify translation, speaker-to-listener playback or the final multi-party meeting.

## Authentication and cloning

The documented STT, TTS, embedding and cloned-synthesis interfaces use the same `X-API-Key-ID` authentication. One Gnani key can cover those features when the account permits them. A configured key is not proof that it is valid or that cloning is enabled. [STT](https://docs.gnani.ai/api/STT/stt-websocket), [TTS](https://docs.gnani.ai/api/TTS/tts-websocket), [embeddings](https://docs.gnani.ai/api/VC/voice-clone-embeddings), [cloned synthesis](https://docs.gnani.ai/api/VC/vc-websocket).

Cloning has two separate billable operations: upload a consenting speaker's clean 5–30-second reference to obtain an embedding, then synthesize using that embedding. The application retains embeddings only for the active session. The standalone check keeps the embedding in memory and never writes it into its report. Never substitute a generated tone or an unrelated person's recording for a consented spoken reference.

Evon hosted API access is a separate account/contract check. The public speech key documentation does not establish an Evon endpoint, model identifier or compatible request schema. [Hosted-beta details](https://www.gnani.ai/evon-waitlist).

## Permission before each flow

After the normal dependency setup, run `npm run dev:checks` and open `/#/usage` at the printed frontend URL (normally `http://127.0.0.1:5180`). The dedicated port avoids mixing this report with another development app on 5173; `CHARCHA_WEB_PORT` can select a different free port. This starts a loopback-only live API with the approval lock enabled; opening it performs no inference. It does not change the saved demo mode or deploy a server. The normal `npm run dev` still follows your saved configuration. Stop either command with Ctrl+C when finished.

`USAGE_REQUIRE_FLOW_APPROVAL=true` is the default. With no active local operator grant, provider reservations fail before an upstream request. Existing daily caps still apply. A grant has one allowlisted purpose, a maximum 300-second lifetime and explicit budgets for all seven resource types; unspecified resources have a zero budget. There is no automatic renewal. Stop unrelated meetings during an approved check, because an unbound meeting can consume the active operator allocation.

`scripts/provider_flow.py` is a **local operator tool**, not a browser endpoint. Use `plan` to review limits without a ledger write or network call. Use `approve --human-approved` only after the human approves that exact flow. Closing or expiring a grant blocks further reservations, including continuing STT metering. The dedicated test runner pins the exact flow ID and closes it after success, failure or cancellation.

From the project folder, these commands only show the prepared plans:

```powershell
.\server\.venv\Scripts\python.exe scripts/check_gnani.py --plan
.\server\.venv\Scripts\python.exe scripts/check_gnani.py --plan --purpose voice_clone_check
```

The standard check synthesizes one short fixed Hindi phrase and sends that generated PCM through one STT connection. It uses no microphone, MT call or enrollment. Its plan shows the exact synthesis-character count, one synthesis attempt, one recognition connection and the conservative connection-time reservation. No automatic provider retries are performed. The cloned-voice check is a separate approval and requires a local reference file plus explicit own-voice consent.

After approval, grant **exactly** the printed plan using `scripts/provider_flow.py approve --human-approved`, then run `scripts/check_gnani.py --run --flow-id <approved-UUID>` with the matching purpose. For a clone check, also supply `--reference <own-reference.wav> --consent-own-voice`. The run command never grants itself permission. Do not run either command with approval flags merely to inspect setup.

## Rupees, programme credits and actual charges

The supplied account pricing table lists **₹27 per hour of STT** and **₹27 per 10,000 TTS characters**. These are different billing units. The earlier ₹0.06/request quote is superseded. The reference calculation is `reserved_STT_seconds × 27 / 3600 + standard_TTS_characters × 27 / 10000`. It is an estimate, not a guaranteed charge or hard rupee cap: billing rounding, character rules, failed/partial requests and posting delay need confirmation. [Account pricing page](https://app.gnani.ai/voice/pricing).

The supplied table does not establish enrollment pricing or whether cloned synthesis has the standard TTS tariff. Cloning estimates therefore remain unknown. Rupees and programme-credit units are kept separate; the reported rupee balance is never relabelled as a number of programme credits.

No documented automatic programme-balance endpoint or credits-charged response field was found in the public speech contracts. The Usage page displays local reserved units and safe timing metadata, plus **manual, timestamped** balance evidence when enabled locally. It never subtracts an estimated charge from the reported balance. After a flow closes, record the dashboard's updated balance with `provider_flow.py reconcile`; the difference is labelled a manual dashboard delta. Other account activity or delayed charges can affect that difference.

The local `balance` command can record a reported starting balance without calling Gnani. Use `INR` for rupees, and `programme_credits` only when the dashboard actually reports that unit. Before/after flow observations must use the same unit and valid chronological timestamps; top-ups cannot be attributed as consumption.

## Reports and measurements

Private test outputs are written under ignored `server/data/gnani-checks/`; that entire runtime data directory is excluded from the source ZIP, Git and Docker build context. Reports contain test status, reserved units and explicitly bounded measurements. They never contain keys, authorization headers or embeddings. The generated output WAV is available for deliberate listening review.

TTS first-PCM time measures server request start to first received PCM chunk. STT check time includes its connection and delivery of the generated test audio until the first final transcript. Neither is audible listener latency. Existing room-stage measurements stay on the Performance page; standalone check measurements appear with the approved flow on Usage. A successful clone response still needs speaker similarity and target-language intelligibility review.

Public usage responses hide manual account balances and reconciliation amounts by default. `USAGE_SHOW_PRIVATE_BALANCE=true` is intended only for an operator-controlled API on `127.0.0.1`; production generation forces it off. Public operator financial reporting would require a separate authentication feature.
