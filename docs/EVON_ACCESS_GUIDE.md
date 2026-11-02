# Find the Evon request details without running a model

The existing account key is retained. Do not create another key or submit a model prompt just to find the integration instructions.

## What is verified

The [speech API reference](https://docs.gnani.ai/api/introduction/introduction) documents STT, TTS and voice cloning. It does not supply the hosted Evon inference route. Gnani's [Evon access page](https://www.gnani.ai/evon-waitlist) describes a closed beta and says selected users receive API access and a quick-start guide by email. This does not establish the entitlement of this particular account either way.

The public [LLM model-list page](https://docs.gnani.ai/Platform/Get_LLM_Models) belongs to Agent Builder configuration. Listing a model for an agent is not a documented standalone Evon translation request. The [Evon model card](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B) also gives self-hosted examples; their localhost address and repository/model name are not proof of the hosted account's URL or model alias.

On 27 October 2026, a read-only inspection of the signed-in account showed the Voice sidebar: **Speech to Text**, **Text to Speech**, **Voice Cloning**, **API Keys**, **Usage**, **Billing**, **Pricing** and **Documentation**. There was no Evon/LLM entry. Documentation opened the speech API introduction linked above. The product switcher offered **Gnani APIs** and **Gnani Agents**. Opening Agents displayed **Unsupported Email Type**, with an official-email requirement for that workspace. No credentials, account changes, model inputs or inference calls were made. These observations do not establish whether the existing key is entitled to Evon.

## Step by step

1. Open **https://app.gnani.ai/voice** in the browser you normally use for Gnani.
2. If redirected to **iamportal.gnani.site**, sign in yourself with the account holding the existing key/credits. The observed sign-in page offers Email/Password, Google and Microsoft. No credentials need to be sent in chat.
3. In the observed Voice sidebar, **Documentation** opens the speech API reference. It does not expose an Evon quick-start. The **Gnani APIs** product switcher also offers **Gnani Agents**, but this account's Agents workspace currently requires an official email. Do not change account details or create an agent to look for an inference endpoint. If Gnani later adds an **Evon** or **LLM** section, inspect its documentation/sample-code view with model inputs empty; do not press Generate, Send, Run or Test.
4. In an Evon request example, identify the **full inference URL**, exact **`model`** value, **authentication header name/scheme**, and expected request/response shape. Copy the documentation link or example with the key removed. Do not substitute a Timbre/Prisma model name or a self-hosted localhost example.
5. If no such section is present, search the registration inbox, spam and promotions for **Evon**, **Gnani**, **closed beta**, **quickstart**, and **quick-start**. The access email is the location explicitly described by Gnani's public beta page. Open the guide linked there.
6. If neither the dashboard nor email supplies it, ask Gnani support to confirm hosted Evon access and provide the inference URL, served model ID, header and billing unit for the existing account. Registering a speech key alone does not reveal those request details. No authenticated API probing is needed to inspect documentation.

There is no verified `Evon → API → Quick-start` path in this account's current dashboard. Use the emailed guide or ask Gnani to supply it; do not infer a hosted endpoint from unrelated speech or Agent Builder routes.

## How the guide maps to this application

The current adapter uses an OpenAI-compatible POST to `EVON_BASE_URL + /chat/completions`, a request `model`, and optional Bearer authentication. These describe the implemented adapter, not a claim that Gnani's hosted beta uses the same contract. If the supplied guide differs, adapt the code first and verify it with mocks.

Keep the existing secret in the server's ignored configuration. Reuse it only with the documented Gnani destination and authentication header. Do not send it to an inferred URL or paste it into reports. The account's Evon rate, billing unit and limits can remain explicitly unknown until supplied; no total charge should be invented from speech prices.

## Next gate

The [Hindi/Tamil plan](HINDI_TAMIL_TEST.md) remains the first two-turn standard-voice check. The [ten-language matrix](LANGUAGE_TEST_MATRIX.md) is an offline coverage plan, not permission to run its ninety directions. Obtain a fresh, specific approval before any paid flow. Voice cloning remains deferred.
