# Temporary Evon testing on Modal

This is a prepared alternative to the GCP GPU VM, using the same pinned Evon model and vLLM image. It keeps standard voices first and voice cloning deferred. Modal credits and GCP credits are separate balances; GCP promotional credits do not fund Modal.

## Five-language stage — 31 October 2026

The [five-language conference stage](FIVE_LANGUAGE_CALLS.md) has its own $5
Modal ceiling and a maximum of ten recorded speech flows. The October 30
budget and snapshots below are historical.

## First approved stage — 30 October 2026

The first **$10 Modal stage** is approved. The saved workspace usage ceiling is
$10, with an effective default $0 net-charge limit while the observed credit
covers that ceiling. The owner renewed CLI profile `artha-mesh` for workspace
`jatin2567`; authenticated billing and App-list checks passed with zero metered
and billed cost and no existing App at preflight. Sign-in is complete. Private
deployment succeeded after the Python correction below. All 13 weight shards
are cached with a committed verification marker, and the A100 loaded the pinned
model. The App is now explicitly stopped with zero active containers. The latest
post-follow-up billing snapshot reports **$1.63964278 metered and $0 billed**; reporting
can lag, so this is not a final invoice. The older dated account
checkpoint below is historical, not the current credit entitlement. Private
refreshed account evidence stays in ignored `work/`.

Use [CONFERENCE_STAGE_ONE.md](CONFERENCE_STAGE_ONE.md) for current camera controls,
local checks and live acceptance order. Screening is off and cloning is deferred.
The corrected sequential local first-audio fixture passed all 20 branches;
continuous, simultaneous and real-device/provider conferencing remain unverified.

### Python compatibility checkpoint

The first image build exposed a real integration issue before GPU allocation:
the pinned vLLM image provides Python 3.12.3 as `python3`, but no `python` command
for Modal detection. The deployment now adds only that command alias, preserving
the existing vLLM/Torch package environment. Serialized functions also require
a matching local Python minor version; the deployment rejects other versions.
Run `scripts/setup_modal.ps1` to prepare the isolated Python 3.12 CLI under
`work/modal-cli-py312/.venv`. It starts no cloud resources or sign-in. Existing
`artha-mesh` profile authentication is shared; no new token is needed while valid.
The compatibility correction passed 38 offline tests. Remote inspection then
confirmed Python 3.12.3, vLLM 0.32 and the existing CUDA Torch environment. The
GPU and model subsequently passed authenticated readiness.

### Bounded download correction

The first CPU Xet transfer was stopped after 1,008.547 seconds with no complete
weight shard and insufficient throughput for the 30-minute preparation cap.
Its failed record is retained separately. This did not allocate a GPU or use
Gnani. The corrected single attempt selects Hugging Face's documented HTTP path
with `HF_HUB_DISABLE_XET=1` and `HF_HUB_DISABLE_SHARED_BLOBS=1` in the download
subprocess only. Parent settings, pins, file allowlists, four workers, CPU limits
and the original session expiry stay unchanged. There is no automatic fallback
or retry. The correction passed 134 focused offline tests. Its first bounded
HTTP run timed out with eight complete shards preserved. A separately reviewed
continuation reused those files and completed in 471.266 seconds: 13 shards,
63,500,753,040 shard-file bytes and a committed verification marker. Neither
failed attempt is counted as a successful download.

### Actual translation and speech checkpoint

The first text check exposed a Hindi echo in the Hindi→Tamil answer. The shared
explicit-target prompt was corrected, and the new two-case check returned the
expected target scripts in **875.225 ms Hindi→Tamil** and **411.614 ms Tamil→Hindi**.
Those are complete-text request timings, not listener audio latency or p95.
The limited script guard is not semantic or language-identification acceptance.

The one approved Gnani flow then completed **Hindi→Tamil** through STT, Evon and
standard-voice TTS. STT start to first target PCM was **5,457.414 ms**, including
STT connection and real-time source upload. This excludes RTC and physical
playback and is not speech-end delay. Tamil→Hindi stopped at STT without a final
transcript; the saved Tamil clip is valid and non-silent, but the failure cause
is unresolved. There was no retry. Meaning review is still pending.

The grant is closed: 19 reserved STT seconds, two connections, one translation
and three TTS requests/132 characters. At the owner-supplied rates the reference
amount is **₹0.4989**; actual Gnani billing and programme-credit conversion are
unknown. No further Gnani request is authorized by that consumed grant. See
`work/modal-stage-01/hindi-tamil-speech/report.json` and **Performance → Saved
checks** for the retained partial result.

The separately approved single Tamil→Hindi follow-up uses
`scripts/check_tamil_hindi_followup.py`. Its plan reuses the existing 3.2-second stock
Tamil clip, explicitly requests Prisma v3.0, reserves one STT connection/25
seconds and permits one translation plus one standard Hindi TTS request/300
characters. Its reference ceiling is **₹0.9975**, with no source TTS, retries,
screening or cloning. It requires a fresh exact grant and flow-bound plan hash.
The previous cloud deadline is not reusable; any approved execution needs a
fresh short session within the remaining $10 stage budget.

### Completed separate Tamil follow-up

The owner approved that exact follow-up. It completed in 10.704 seconds with no
retries, cloning or screening. The fixed 3.2-second clip was recognized and
translated to **“मुझे नीली किताब चाहिए, लाल नहीं।”** before standard Hindi
synthesis. Meaning acceptance and human-speech accuracy still require review.
Prisma v3.0 was explicitly requested; the provider did not echo a served-model
confirmation. Both that request and the longer recognition deadline differ
from the original failed run, so success does not isolate its failure cause.

| Recorded boundary | Time |
| --- | ---: |
| STT start → final transcript receipt | 5,560.990 ms |
| Translation → complete text | 1,443.544 ms |
| Target TTS → first PCM | 484.172 ms |
| STT start → first target PCM | 7,488.745 ms |
| STT start → complete target PCM | 8,752.070 ms |

STT receipt excludes WebSocket close. The full chain includes connection setup,
real-time clip transmission and closing recognition before translation. These
are not speech-end or audible-listener timings; do not subtract the clip length
and relabel the result. One observation per condition cannot establish p95 or
an optimization result. A proposed project goal is under two seconds from
speech end to audible translated speech on a warm service; it is not yet tested.

Usage was six reserved STT seconds/one connection, one translation/46 source
characters and one TTS request/32 characters: **₹0.1314 reference**, with actual
Gnani charges unknown. The grant is closed. The new report is
`work/modal-stage-01/tamil-hindi-followup-20261030/report.json`; the original
two-case partial report remains unchanged. Both records are visible separately
in **Performance → Saved checks** and **Usage & limits → Saved speech tests**.

The follow-up's fresh cloud window retained its original 30-minute deadline.
A local status parser initially omitted `app info --json`; this stopped
preparation before any health request, grant or Gnani usage. The explicit
correction preserved the deadline and original logs. Model readiness then took
215.667 seconds (one HTTP 303 continuation followed by 200), separate from speech
latency. Final read-only verification confirms the owned App stopped and zero
active containers. The latest billing snapshot is provisional, about **$1.64
metered/$0 billed** across the stage; it is not an exact per-flow compute charge.

## Proposed working-demo sequence — 29 October 2026

If the owner supplies at least $40 of applicable custom-compute credits, use
Modal for the Evon translation model while keeping the application/LiveKit and
experimental screening local during device testing. This is a recommendation,
not a new GPU launch approval or a verified account balance. The dated account
checkpoint below remains historical evidence until refreshed by the owner.

| Proposed ceiling | Work to validate |
| --- | --- |
| $10 | CPU cache preparation, GPU/image compatibility, authenticated model health and one Hindi↔Tamil standard-voice flow |
| $15 | Expand to the prepared five-language, 20-direction translation matrix; retain failures and separate first/warm samples |
| $10 | Two-device and three-participant routing, reconnect and concurrency regressions |
| $5 | Reserve for a bounded final demonstration or a specifically reviewed failed-stage retry |

These are allocation ceilings, not quoted costs or a guarantee of completing
every stage. Start with the first stage and review its actual result before
expanding; do not keep a GPU warm between unplanned sessions. Gnani speech
requests have a separate provider balance and require the previously agreed
bounded-flow approval. Modal compute credits do not pay that invoice.

On 29 October, Modal's [pricing](https://modal.com/pricing) lists A100 80 GB at
$0.000694/second (about $2.50/GPU-hour), plus CPU, RAM and any regional multiplier.
Application load and idle scale-down time can be billable. The prepared
one-container function uses custom GPU compute, not a separately billed shared
model endpoint. Confirm applicable workspace credit and spending controls before
execution; the public credit offer does not establish this account's entitlement.

The immediate deliverable is a working standard-voice meeting demo, an interface
with stage/receiver timing boundaries and exportable test results, and an honest
experimental screening view. The [public human pilot](PUBLIC_HUMAN_SCREENING.md)
found 14 false alarms and 12 unknowns in 50 genuine clips, so screening should
remain a warning/monitoring experiment while its operating point and domain
performance are investigated. No reliable automatic blocking, reduced-window
accuracy, production readiness or voice-cloning acceptance is established.

## Account checkpoint — 28 October 2026

The local CLI is installed as **Modal 1.6.3** in `work/modal-cli/.venv`, independently of the API environment, using `deploy/modal/requirements.txt`. The owner completed authentication for profile `artha-mesh`, workspace `jatin2567`. The read-only billing summary reported zero metered and billed cost.

**The signed-in workspace currently shows only $1 of included compute credits per month**, `$0 / $1` usage, a usage limit set by Modal, and an **Add payment method** prompt. Its Credits tab also states $1 monthly credit. This actual account view takes precedence over the public Starter page advertising $30/month. Adding a payment method must not be assumed to grant $30 automatically.

No App has been built, deployed or invoked for this project; no CPU weight download or GPU inference has run. The first two-hour compute proposal below exceeds the verified $1 account allowance, before other charges. Payment setup, any change to credit entitlement and a verified credits-only spend limit are still owner/account steps. Do not start the prepared cloud flow while those checks are unresolved.

The reference claiming “no card required”, “no quota gates”, “eight free A100 hours” and “7200 seconds caps the whole deployment” is not reliable. Modal currently requires a valid payment method for GPU use, has allocation/concurrency limits, and separately bills resources. A Function execution timeout is not an App lifetime limit. Sources: [GPU access](https://modal.com/docs/guide/gpu), [billing](https://modal.com/docs/guide/billing), [timeouts](https://modal.com/docs/guide/timeouts).

## Prepared implementation

| Item | Prepared behaviour |
| --- | --- |
| Deployment | `scripts/modal_evon.py`, App `artha-evon-test`; importing constructs lazy Modal handles and does not invoke the cloud functions. A real deployment can still build an image and incur costs. |
| Lifecycle helpers | `scripts/modal_evon_runtime.py`; import performs no I/O. It validates the pinned inputs, checks the cache and GPU, starts vLLM, waits for real health and supervises its process group. |
| Model | `gnani/gnani-evon-v3.3-30B-A3B`, revision `fb9ddb6b58f2d235684388a9260671fca5ebccaf`; native architecture with remote model code disabled. |
| Container | The immutable image in `deploy/evon/inputs.verified-2026-10-28.json`, with the model/runtime metadata in `deploy/evon/pins.verified-2026-10-28.json`. A100 runtime and model loading passed in this stage. |
| CPU preparation | Explicit `download_weights` call, two physical CPU cores, 4 GiB RAM, no GPU, one container, zero retries, at most 30 minutes and never beyond session expiry. |
| Shared cache | Volume v2 `artha-evon-weights-v2`. The CPU task downloads the pinned snapshot, validates metadata hashes and the presence/size of all 13 shards, then commits a completion marker. This is not an independent tensor-hash audit. |
| Serving | One A100 80 GB, four physical CPU cores, 64 GiB RAM, 4096-token context, at most two model sequences. GPU startup checks reject an undersized/different GPU or driver below R580. |
| Scaling | Maximum one serving container, zero minimum/buffer containers, 300-second GPU idle scale-down window; CPU preparation retains 30 seconds. Idle warm time can still consume compute. Stop explicitly between sessions. |
| Network | HTTPS Web Function with Modal proxy authentication, plus a separate vLLM key. No unauthenticated inference endpoint. |
| Deadline | `MODAL_EVON_SESSION_EXPIRES_AT`: one absolute UTC timestamp, at least 60 seconds and at most two hours ahead at deployment. Container restarts do not renew it. The runtime watchdog stops the vLLM process group at expiry. |

The GPU function reads the committed cache without downloading weights and mounts it read-only. This avoids paying GPU time for the initial 63.5 GB transfer. Failed or incomplete CPU preparation must be corrected before starting the GPU. [Modal model-weight guidance](https://modal.com/docs/guide/model-weights).

The deadline is a lifecycle guard, not a provider-wide invoice cap: a deployed endpoint still needs explicit shutdown, failed/restarted containers may incur overhead, and persistent storage can outlive the App. Do not silently extend the timestamp or redeploy to fund a retry.

## Credit and geography checks before deployment

1. In the actual workspace's **Usage & Billing**, verify the available credit, cycle/reset details, usage already charged and applicable restrictions. Preserve a private record of these values; no payment details belong in project reports.
2. The owner handles any payment-method setup. Recheck the resulting credit grant instead of substituting the public $30 offer for the displayed $1.
3. Verify a **custom Workspace spend limit of $0** if the account UI permits it. Modal distinguishes the net out-of-pocket spend limit from the Workspace usage budget, which counts usage before credits. Its documented default spend limit can allow bank/card charges. A zero billed-cost summary is historical evidence, not proof that the limit is configured.
4. Set a modest total usage budget within verified applicable credits, allowing CPU preparation, image build, storage, startup, serving and shutdown overhead. Stop if the account does not permit the required credits-only controls; do not make an unconditional “no bank charges” promise.
5. Record the selected region and price multiplier. The prepared container region is broad **`ap`** at 1.15×; request routing is **`ap-south`**, Mumbai. This permits other Asia-Pacific container locations. GPU capacity in the selected pool is not guaranteed.

Modal application logs can be stored in the United States, and request/storage routing has additional residency rules. This temporary test is **not evidence of complete India-only residency**. Final sovereign hosting remains the separate Yotta deployment. [Budgets and spend limits](https://modal.com/docs/guide/budgets), [regions and multipliers](https://modal.com/docs/guide/region-selection), [data residency](https://modal.com/docs/guide/data-residency).

### Reference cost for this profile

The authenticated rates saved in `work/modal-cli/billing-rates.json` were A100 80 GB **$2.50/hour**, physical CPU **$0.0473/core/hour**, memory **$0.008/GiB/hour**, and volume storage **$0.09/GiB/month**. These are observed USD rates, not a rupee conversion or a charge record.

For the configured GPU profile:

```text
(2.50 + 4 × 0.0473 + 64 × 0.008) × 1.15 = $3.68138/hour
Two hours of that allocation = $7.36276
```

This excludes CPU download, image-build work, storage, egress and any other workspace usage. Startup and idle retention consume the allocation too. The persistent cache can continue to incur storage cost after serving stops; inspect actual storage allowances rather than assuming it is free. Rates and credits must be checked again before execution. [Pricing](https://modal.com/pricing), [billing reports](https://modal.com/docs/cli/latest/billing), [volume billing](https://modal.com/docs/guide/volumes).

The 30 October pricing check lists **up to 1 TiB of included Volume storage**.
A read-only inventory found one environment and only this stage's named cache.
The pinned model is far below that allowance. Retain the verified public cache
for the next planned test while stopping the App; check its final size and the
current allowance again before a later session. This avoids another large
download. Above-allowance storage and changed account terms still need review.

## Ordered test flow

The commands below are an execution guide, not a record that they have been run. Start in the repository root in PowerShell. Steps that build, invoke or contact an endpoint can consume Modal credits. Gnani STT/TTS remains separately gated and is not invoked by this text-only flow.

### 1. Verify local preparation

```powershell
.\server\.venv\Scripts\python.exe -m pytest server/tests/test_modal_evon.py server/tests/test_modal_proxy_auth.py server/tests/test_evon_benchmark.py -q --basetemp work/pytest-modal-guide
```

These tests use local fixtures and provider doubles; passing them does not establish remote model loading, translation quality or live latency. Use a fresh temporary folder if it is already in use.

The isolated CLI is already installed. On another checkout, install the pinned tools into a dedicated environment using `deploy/modal/requirements.txt`, then run `modal setup` from that environment. The owner completes browser authentication; do not paste a Modal login token into chat or application configuration. [Setup](https://modal.com/docs/guide/getting-started).

### 2. Verify the selected workspace and billing controls

```powershell
.\work\modal-cli-py312\.venv\Scripts\modal.exe token info --profile artha-mesh
.\work\modal-cli-py312\.venv\Scripts\modal.exe billing summary --profile artha-mesh --json
.\work\modal-cli-py312\.venv\Scripts\modal.exe billing rates --profile artha-mesh --json
```

Confirm the intended profile/workspace and complete the account checks above. The owner-selected authentication token expires; an expired token requires a fresh owner login. Do not print token files, private environment files, card information or credentials in diagnostic output.

### 3. Prepare private inference credentials

This profile has two independent authentication layers:

| Destination | Required credentials |
| --- | --- |
| Modal's edge proxy | Proxy token ID/secret pair in `Modal-Key` and `Modal-Secret`. These are not the Modal CLI/API login credentials. |
| vLLM inference server | A separately generated, URL-safe `VLLM_API_KEY` of 32–256 characters. Never reuse the Gnani speech key. |

Create the Modal Secret **`artha-evon-inference`** with `VLLM_API_KEY`. Use a private ignored JSON object containing only that key, not a command-line key literal. For example, after securely preparing `work/modal-private/inference.json`:

```powershell
.\work\modal-cli-py312\.venv\Scripts\modal.exe secret create artha-evon-inference --profile artha-mesh --from-json work/modal-private/inference.json
```

Create or select the intended Modal proxy token through the owner's approved credential workflow. The CLI creation command prints its secret, so do not run it into a captured transcript; use the dashboard or a helper that writes directly to a private file without printing. Store client credentials in a private ignored JSON file, such as `work/modal-private/client.json`, with fields `api_key`, `modal_key` and `modal_secret`. Restrict local file access to the owner. Do not copy the private directory into the deployment image.

For the benchmark process, load the file without displaying it:

```powershell
$evonPrivate = Get-Content -LiteralPath work/modal-private/client.json -Raw | ConvertFrom-Json
$env:EVON_BENCHMARK_API_KEY = $evonPrivate.api_key
$env:EVON_BENCHMARK_MODAL_KEY = $evonPrivate.modal_key
$env:EVON_BENCHMARK_MODAL_SECRET = $evonPrivate.modal_secret
```

The benchmark does **not** read `.env`. The meeting API later uses server-only `EVON_API_KEY`, `EVON_MODAL_KEY`, `EVON_MODAL_SECRET` and `EVON_BASE_URL`; proxy headers are allowed only for HTTPS `*.modal.run` destinations. Keep all keys out of the frontend and exported plans. [Modal proxy authentication](https://modal.com/docs/guide/webhook-proxy-auth), [Secret file import](https://modal.com/docs/cli/latest/secret).

### 4. Set one reviewed deadline, then deploy

Only after credit eligibility, spend limit, credentials and the intended session are reviewed, set an absolute deadline. This example allows 110 minutes from now, including preparation:

```powershell
$env:MODAL_EVON_SESSION_EXPIRES_AT = [DateTime]::UtcNow.AddMinutes(110).ToString('yyyy-MM-ddTHH:mm:ssZ')
.\work\modal-cli-py312\.venv\Scripts\modal.exe deploy --profile artha-mesh scripts/modal_evon.py
```

Deployment may build and store an image. It does not explicitly call the CPU download function or inference. Keep the emitted exact App identity and endpoint URL. Do not deploy into a different profile merely because authentication failed.

Read the new deployment's exact identity with
`modal app info artha-evon-test --json --profile artha-mesh` from the same CLI.
Redeploying after stopping can create a new App ID; never assume a previous
stage's stopped ID identifies the current deployment.

### 5. Download and verify the cache explicitly on CPU

```powershell
.\work\modal-cli-py312\.venv\Scripts\modal.exe run --profile artha-mesh scripts/modal_evon.py::download_weights
```

This is a real cloud CPU invocation and weight download. Inspect its completion record before serving: pinned revision/metadata, 13 nonempty complete shard files, expected tensor size, tokenizer and committed marker. Preserve failures; do not retry automatically or extend the session to conceal a failed preparation.

### 6. Check authenticated readiness before timing translations

Use the exact deployed HTTPS host plus `/v1` as the base URL, not the Modal dashboard URL. The first authenticated `/health` request can allocate the A100 and load/compile the model, consuming credits even though it is not a generation request. Wait for genuine readiness and record startup separately from warm request latency. Do not use the first translation request as an unbounded warm-up or enable automatic HTTP retries.

The runtime itself waits for vLLM `/health` within the startup/deadline bound and verifies the GPU before reporting startup success. If readiness fails, stop and inspect the controlled failure; a port accepting a connection alone does not prove model readiness.

Use the bounded helper to handle Modal's same-request HTTP 303 continuation.
First inspect its plan (no network):

```powershell
$evonHost = 'https://REPLACE_WITH_DEPLOYED_HOST.modal.run'
.\server\.venv\Scripts\python.exe scripts/check_modal_readiness.py --base-url $evonHost
```

Only during a reviewed compute session, use `--run --acknowledge-gpu-cost` with
the private credentials file and a fresh result path. The helper accepts only
same-origin `/health` continuations, at most six within 960 seconds, and never
exports their private query. It makes no inference or Gnani request. A 303
alone does not prove a failed startup. [Modal request timeouts](https://modal.com/docs/guide/webhook-timeouts).

### 7. Review and execute the bounded text plan

Set the non-secret endpoint base, replacing the placeholder with the exact deployed URL:

```powershell
$evonBaseUrl = 'https://REPLACE_WITH_DEPLOYED_HOST.modal.run/v1'
.\server\.venv\Scripts\python.exe scripts/evon_benchmark.py --endpoint $evonBaseUrl --output work/evon/plan-modal.json
```

This command only writes an offline plan. The current default covers two draft ordinary-conversation cases, Hindi→Tamil and Tamil→Hindi: at most two requests, 256 output tokens each, 30 seconds per request, 120 seconds for the runner, no automatic retries, STT, TTS or voice cloning. Review its exact `plan_sha256`, endpoint and cases before execution. Corrected cases or limits require a fresh plan/hash.

Only after that exact flow is approved, use its hash and a fresh output filename:

```powershell
.\server\.venv\Scripts\python.exe scripts/evon_benchmark.py --endpoint $evonBaseUrl --execute --approve-plan REVIEWED_PLAN_SHA256 --acknowledge-gpu-cost --output work/evon/result-modal.json
```

Complete responses still need bilingual meaning review. Report text request time separately from startup, speech recognition, synthesis and physical listener delay. HTTP success and an offline test pass are not a five-language E2E acceptance result. After this first text check passes, use [the five-language speech plan](FIVE_LANGUAGE_TESTING.md), with each concrete Gnani flow approved separately; follow [screening evaluation](FIVE_LANGUAGE_SCREENING.md) after the latency baseline.

### 8. Stop the App and decide the cache lifecycle

Stop the exact owned App when finished or on a blocking failure; do not rely only on closing the local terminal or waiting for idle scale-down:

```powershell
$evonAppId = 'REPLACE_WITH_EXACT_APP_ID_FROM_THIS_DEPLOYMENT'
.\work\modal-cli-py312\.venv\Scripts\modal.exe app stop $evonAppId --yes --profile artha-mesh
.\work\modal-cli-py312\.venv\Scripts\modal.exe app info $evonAppId --json --profile artha-mesh
.\work\modal-cli-py312\.venv\Scripts\modal.exe container list --profile artha-mesh --json
.\work\modal-cli-py312\.venv\Scripts\modal.exe billing summary --profile artha-mesh --json
```

Check the stopped state and reconcile usage again after billing data has settled. Expiry is not a reason to omit explicit shutdown. App stop does not delete `artha-evon-weights-v2`. Retain it only within a verified included allowance or an approved storage budget; the current checkpoint above supports keeping this public cache for the next test. If cleanup becomes necessary, save the reports first and delete only that exact cache. Modal says deleted volume data may still be billed for up to four days. Revoke temporary endpoint credentials when no longer needed. [Stopping Apps](https://modal.com/docs/cli/latest/app), [persistent volumes](https://modal.com/docs/guide/volumes).

## What remains unverified

- Final reconciled stage charges. The latest post-follow-up snapshot is $1.63964278 metered/$0 billed; the dated $1 checkpoint is superseded. The effective default $0 net limit remains distinct from a saved custom limit.
- The original Tamil failure's root cause and provider-confirmed STT model. The separately approved follow-up completed; both grants are closed and further speech needs new approval.
- Bilingual meaning review, the five-language provider matrix, physical listener audio E2E latency, two-device acceptance and independently labelled detector accuracy.

The checkpoint above records preparation actually executed; the ordered commands
remain a guide, not evidence that every acceptance step passed. Voice cloning
remains later work.
