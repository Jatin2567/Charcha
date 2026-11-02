# Hindi–Tamil with standard voices

## Current result and next diagnostic — 30 October 2026

Evon is now self-hosted for the temporary test on Modal; no hosted-beta
quickstart or new Gnani key is needed for that path. The A100 loaded the pinned
model and both corrected text directions completed. One approved provider flow
completed Hindi→Tamil, while Tamil→Hindi stopped at STT without a final
transcript. The separately approved fixed-clip follow-up subsequently completed
Tamil→Hindi. Both grants are closed. The detailed results and timing
boundaries are in **Performance → Saved checks** and
[MODAL_TESTING.md](MODAL_TESTING.md).

Offline inspection found the existing Tamil source valid, non-silent mono
PCM16 at 16 kHz. The historical result did not retain an exception category,
so its precise failure cause remains unknown. The new runner records a safe
error category. It explicitly requests Prisma v3.0 through the WebSocket
upgrade `model` header, as documented in [Gnani streaming STT](https://docs.gnani.ai/api/STT/stt-websocket#prisma-v3-0-on-streaming).
The `/stt/v3/stream` URL alone does not select that model. A requested model is
recorded separately from a provider-confirmed model; the latter remains unknown
unless the provider actually reports it.

Print the diagnostic's plan without settings, a ledger or network access:

```powershell
.\server\.venv\Scripts\python.exe scripts/check_tamil_hindi_followup.py
```

The approved diagnostic used the **existing 3.2-second source clip** with these caps:

| Resource | Maximum |
| --- | ---: |
| STT connections / reserved seconds | 1 / 25 |
| Recognition deadline / separate close deadline | 18 / 3 seconds |
| Translation requests / source characters | 1 / 500 |
| Target standard Hindi TTS requests / characters | 1 / 300 |
| Source TTS / retries / enrollments | 0 / 0 / 0 |
| Grant lifetime / provider-work deadline | 180 / 110 seconds |

The reference ceiling at the supplied rates is **₹0.9975**, excluding unverified
rounding/taxes and separate Modal compute. The runner binds the endpoint, input
hash, prompt and exact fresh grant to a reviewed plan hash, and never creates
its own approval. The single approved execution completed: STT receipt
5,560.990 ms, MT 1,443.544 ms, target first PCM 484.172 ms, full-chain first PCM
7,488.745 ms. It used six reserved STT seconds, one translation/46 characters and
one TTS request/32 characters, corresponding to **₹0.1314 reference**, not a
verified invoice. Both grants are now consumed/closed. New execution needs a
new explicit approval; reusing either grant or rerunning the previous flow is
not permitted. Keep
screening and voice cloning off. An actual microphone/receiver check and
bilingual meaning review remain separate acceptance steps.

## Earlier typed-only proposal — retained for reference

The following proposal predates the self-hosted Modal stage. It describes the
hosted-beta alternative and is not the current missing input or an active grant.

The user reported the local original-audio check complete. The next gate is a small **typed translation and standard-speech pair**. Keep microphones off so STT is not introduced before MT/TTS has been checked. Voice cloning remains deferred. Preparing this plan makes no provider call and grants no permission.

## Evon information still needed

Use the **existing Gnani key**; no second key is requested. We need the official Evon quickstart or a request/response example with secrets removed, showing:

1. The inference base URL and HTTP route. The current adapter appends `/chat/completions` to `EVON_BASE_URL`; include a `/v1` prefix only if the documented endpoint uses it.
2. The exact served model identifier, as expected in the request's `model` field. A public model/repository name does not establish this server value.
3. The authentication header/scheme for using the existing key. The current adapter supports Bearer authentication; a different documented Gnani header requires an adapter change before testing.
4. The request and response shape, plus any required beta parameters, pricing and rate limits supplied in that quickstart.

The application currently expects a non-streaming OpenAI-compatible chat-completion response in `choices[0].message.content`. That is the adapter contract, not an assertion that the hosted Gnani beta uses this exact schema. Reuse the existing secret only against the documented Gnani endpoint and required header; no provider probe is needed to inspect these instructions. Store keys only in the private server configuration.

Gnani's [official Evon API beta page](https://www.gnani.ai/evon-waitlist) says selected builders receive API access and a quickstart by email. That quickstart is the useful missing input here. The saved project configuration alone does not identify the account's Evon endpoint or served model.

## Print the offline plan

```powershell
.\server\.venv\Scripts\python.exe scripts/plan_translation_test.py
```

This standalone script reads no application settings or environment file, imports no provider client, opens no ledger and makes no network or audio request. It prints ASCII-safe JSON containing the exact Unicode phrases, semantic checks, stable case IDs and SHA-256 content hashes. It supports no run or approval action.

## Two fixed turns, one at a time

Join a fresh local interpretation room from the existing two independent browser sessions only after the endpoint contract is configured and this exact flow is approved. Asha chooses **Hindi**, Kavya chooses **Tamil**, and both retain **standard voice** with microphones off. Use model `timbre-v2.5` with **Trisha for Tamil output** and **Nalini for Hindi output**, following the [documented voice catalog](https://docs.gnani.ai/api/TTS/available-voices). Account-specific availability still needs the approved real test.

The nonsecret standard-voice configuration for this plan is:

```dotenv
TIMBRE_MODEL=timbre-v2.5
TIMBRE_VOICE_HI=Nalini
TIMBRE_VOICE_TA=Trisha
```

| Case                 | Sender and typed phrase                                      | Meaning to preserve                                                    | Receiver                                                         |
| -------------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `hi-ta-meeting-time` | Asha: **हम 10 बजे मिलेंगे, 11 बजे नहीं।**                    | Meet at **10**; **11** is rejected. Do not invent a date or time zone. | Kavya hears Tamil standard speech; Asha receives no self output. |
| `ta-hi-book-colour`  | Kavya: **எனக்கு நீலப் புத்தகம் வேண்டும், சிவப்பு வேண்டாம்.** | The speaker wants the **blue book**, and rejects **red**.              | Asha hears Hindi standard speech; Kavya receives no self output. |

The phrases contain **31 + 49 = 80 Unicode codepoints** as counted by the current Python adapter. A bilingual reviewer should accept equivalent natural wording, rather than demand an identical reference translation. These are everyday semantic review prompts, not certified benchmark gold text.

## Proposed first approval, not granted

The proposed grant lasts **120 seconds** and allows only these two typed turns:

| Resource                                       |                                       Cap |
| ---------------------------------------------- | ----------------------------------------: |
| STT connections / connected seconds            |                                 **0 / 0** |
| MT attempts / source characters                |                                **2 / 80** |
| Standard TTS attempts / synthesized characters | **2 / 400**, combined across both outputs |
| Voice enrollments                              |                                     **0** |
| Automatic retries                              |                                     **0** |

The existing operator tool can display those limits without approving or running anything:

```powershell
.\server\.venv\Scripts\python.exe scripts/provider_flow.py plan --purpose live_interpretation --seconds 120 --mt-requests 2 --mt-characters 80 --tts-requests 2 --tts-characters 400
```

At the user-supplied standard TTS reference rate of ₹27 per 10,000 characters, filling the 400-character allowance corresponds to **₹1.08 before unverified billing rounding**. Evon pricing and programme-credit conversion remain unknown until supplied; this is not a guaranteed total invoice or an automatic account-balance deduction. Before any paid operation, present the known/unknown charges and these exact limits, then obtain explicit approval. Do not create a grant during preparation.

Only the two test members should be present, and no unrelated live room should be active: the application's operator grant is shared. If a translation exceeds the remaining TTS character allowance, synthesis is blocked rather than silently expanding the grant. On a failure, unexpected output or exhausted allowance, stop; do not resubmit, retry or renew automatically.

## Record the result

For each turn, preserve the case ID, source and translated text, target-language listening result, number/negation checks, and complete/error status. Export the room's **Performance** timings and **Usage** reservations. Typed input has no STT timing. First-PCM server timing includes dispatch/subscription preparation; it does not establish physical listener delay. Record listener delay only with a described shared-timebase measurement, otherwise leave it unknown.

After both typed directions pass, prepare a **separate microphone test and approval** to add STT. Do not unmute under the typed-only grant. Voice enrollment and cloned synthesis remain later work.

`npm run dev:local` intentionally remains provider-free original audio. `npm run dev:checks` is a live reporting launcher and does not start the local LiveKit media server. Do not switch launchers, modify the saved mode or enable paid interpretation merely to inspect this plan. Complete the verified endpoint configuration and approval step first.
