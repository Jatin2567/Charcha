# Evon preparation and a bounded GPU test

The default benchmark is offline and uses no GPU, network, provider key or speech service. This package prepares a text-only Hindi↔Tamil test for a later owner-approved GPU session. It does not provision a GCP/Yotta machine, request quota, install Docker, download weights, or start inference. Voice cloning remains deferred.

## Prepare and review locally now

### GCP access checkpoint — 28 October 2026

Project `artha-mesh` is active and Compute Engine is enabled. Billing is linked; promotional-credit eligibility and account type have not been established. The owner authorized **₹5,000 total GCP charges, with a ₹2,500 latency-stage sub-cap** and ₹2,500 reserved for later. These are authorization limits, not a GCP-enforced monetary cap.

Both global GPUs and Singapore A100 80 GB quota were zero. Cloud Quotas reports `NOT_ENOUGH_USAGE_HISTORY`. A no-cost request for **one global GPU**, preference `artha-mesh-single-gpu`, was submitted and completed with `grantedValue: 0`; it is **declined, not pending**. The regional increase was not submitted after the global rejection. A subsequent project instance listing was empty. No billing upgrade, GPU VM, model inference or speech request was performed in this check.

GPU quota is resource permission, not a second credit balance. **The owner subsequently instructed us to treat quotas as fixed and use only existing capacity. No further quota-increase requests are planned.** The prepared Compute Engine candidate needs one global GPU and one `NVIDIA_A100_80GB_GPUS` in `asia-southeast1`; catalog presence is not a capacity reservation. A regional legacy GPU quota of one does not override the global limit of zero. [Compute allocation quotas](https://docs.cloud.google.com/compute/resource-usage).

### Fixed-quota alternatives checked — 28 October 2026

Read-only inspection checked Compute GPU-family quotas, independent Cloud Run allocations and this laptop. No API service was enabled, paid resource deployed, model weights downloaded or inference called during this review. Raw quota snapshots and a compact decision record are under `work/five-language/`.

| Option | Existing facts | Decision |
| --- | --- | --- |
| Compute Engine Evon BF16 | Global GPU limit and use remain 0; A100 80 GB regional limit is 0. GPU-family information supplies no usable positive grant. | Do not attempt a VM. Multiple sequential requests, Spot or another region cannot make a zero global allocation usable. |
| Cloud Run RTX PRO 6000, Delhi or Singapore | Google documents 96 GB VRAM, 20 CPU and **at least 80 GiB host RAM**, with an initial nonredundant GPU grant at first deployment subject to CPU/memory capacity. This account reports CPU allocation 20,000 millicores and **42,949,672,960 bytes = 40 GiB memory** in both regions; no positive GPU grant is verified. | The existing memory allocation is below the required 80 GiB. Do not deploy merely to trigger an initial GPU grant. This separate product is a legitimate alternative only when its full requirements are permitted. |
| Cloud Run L4 | 24 GB VRAM; the pinned BF16 weight index contains **63,499,950,464 bytes** before runtime overhead. | The current single-GPU profile does not fit. Do not silently add CPU offload or quantization and call it the same latency benchmark. |
| Laptop Evon | i5-1235U, about 15.7 GiB physical RAM, Intel Iris Xe integrated graphics. | Keep local transport and CPU detector checks here; it is unsuitable for this BF16 model's memory requirement. |
| Community Evon GGUF | A gated community conversion exists, uses a different upstream revision, and starts at 16.81 GiB before runtime overhead. CPU-only speed and five-language quality are unverified. | Not a ready fallback for this laptop or an approved artifact substitution. Quantization/access/runtime would require a separate review before spending on an experiment. |

The cost-efficient decision with these fixed limits is **zero rental spend** until a compatible permitted GPU endpoint is available, such as the planned Yotta host or an explicitly supplied Gnani Evon endpoint. Retain the ₹2,500 latency allowance for actual model acceptance and E2E speech work. CPU, stub and synthetic checks must not be reported as a GPU translation latency baseline. Voice cloning stays deferred.

Sources: [Cloud Run GPU requirements and supported regions](https://docs.cloud.google.com/run/docs/configuring/services/gpu), [initial allocation depends on CPU/memory capacity](https://docs.cloud.google.com/run/docs/configuring/jobs/gpu), [large-model loading guidance](https://docs.cloud.google.com/run/docs/configuring/services/gpu-best-practices), [official Evon model card](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B), [community GGUF evidence](https://huggingface.co/luminenio/gnani-evon-v3.3-30B-A3B-GGUF).

The five-language latency plan and separate screening protocol are in [FIVE_LANGUAGE_TESTING.md](FIVE_LANGUAGE_TESTING.md) and [FIVE_LANGUAGE_SCREENING.md](FIVE_LANGUAGE_SCREENING.md). Voice cloning remains deferred.

### Alternative host: Modal

The same model/image pins now have a separate [Modal preparation guide](MODAL_TESTING.md), explicit CPU cache download and authenticated, time-bounded A100 service. The local SDK is installed separately from the meeting API. The owner's workspace currently advertises **$1/month included compute and a $1 usage limit**, with a prompt to add a payment method, despite the public Starter page advertising $30/month. No cloud app, model download or inference has run. Account eligibility, applicable remaining credits and a verified zero out-of-pocket spending limit must be resolved before execution. The GCP ceilings above do not become a Modal spending authorization or a currency conversion.

From the repository root in PowerShell:

```powershell
.\server\.venv\Scripts\python.exe scripts/evon_benchmark.py --output work/evon/plan.json
```

The default plan selects `hi-ta-01` and `ta-hi-01` from the existing everyday conversation corpus. It reserves at most two text requests, 256 output tokens each, 30 seconds per request and 120 seconds for the run; no retries, STT, TTS or enrollment. The exact case text, meanings, endpoint fingerprint, served model and limits are covered by `plan_sha256`. Changing any of them requires reviewing a fresh plan. Existing output files are never overwritten.

Select other cases using repeated `--case` arguments, up to 18 distinct cases. The case reference translations are **unreviewed drafts**. A bilingual listener must evaluate names, number associations, negation, conditions, naturalness and intended meaning; matching a reference string is not the acceptance criterion. Numeric-presence checks are only diagnostic and do not prove meaning preservation.

This runner is independent of the app's `/usage` approval ledger. Exported results record actual attempted text calls, failed/unattempted cases and unknown monetary charges. They do not deduct a fabricated Gnani balance. GPU time and any hosted endpoint charges must be reconciled against their own billing records.

## GPU prerequisites, before starting the rental clock

- The public model revision and image digest have now been resolved; see the verified metadata below. Access was ungated when checked, but availability may change. The selected profile keeps model remote-code execution disabled.
- Select a Linux GPU VM and verify the exact hourly price, region, quota, available capacity, storage/egress charges and credit eligibility with the owner. An 80 GB A100/H100 is an initial BF16 target for short context and low concurrency, not a verified capacity promise.
- Prepare Docker Engine, NVIDIA Container Toolkit and Docker Compose 2.30+ through the host's supported installation path. The pinned candidate is vLLM `v0.32.0`, Linux AMD64, CUDA 13.0.2. Use an R580+ NVIDIA driver for this initial profile. An older driver/forward-compatibility arrangement needs separate validation. The existing unpinned `local-evon` Compose profile has been removed. Runtime compatibility is still untested.
- Keep the CPU meeting stack and GPU service separate. The temporary text test needs only the GPU service. Running full speech later requires its own Gnani flow approval.
- Agree on a time and cost limit. Set the provider's VM stop schedule or maximum runtime **before** starting. A budget alert alone does not stop a VM. Downloads, image pulls, model load and idle periods all consume rented runtime. A request timeout does not necessarily cancel server-side generation.

## Generate the portable serving configuration

The public metadata-verified inputs are `deploy/evon/inputs.verified-2026-10-28.json`. Generate a new configuration offline without pulling the image or model:

```powershell
.\server\.venv\Scripts\python.exe scripts/evon_prepare.py --config deploy/evon/inputs.verified-2026-10-28.json --output work/evon/gpu-ready/compose.json
```

The result has one GPU, BF16, 4,096-token context, two concurrent sequences, restart disabled, a persistent model cache, and **host loopback binding only**. Model and tokenizer revisions are pinned; `trust_remote_code` stays false. These are conservative test settings; an actual GPU run must confirm memory use and compatibility. Keep `inputs.example.json` only as a template for a separately reviewed future pin change. ARM64 GPUs such as H100 on a Grace system require a different verified image manifest.

## Verified metadata, 28 October 2026

| Item | Recorded evidence |
| --- | --- |
| Evon repository | `gnani/gnani-evon-v3.3-30B-A3B` |
| Immutable model/tokenizer commit | `fb9ddb6b58f2d235684388a9260671fca5ebccaf` |
| Tensor bytes in the index | `63,499,950,464` bytes, approximately 63.50 GB; this is not total runtime GPU memory |
| vLLM candidate | Official `v0.32.0` release, Linux AMD64 manifest |
| Immutable image | `vllm/vllm-openai@sha256:6ee133356d49ed24cee03dd0cda3d3980279a11c107ce3e752c89e76540f41c9` |
| Image metadata | Docker Hub tag agrees with registry manifest SHA and `Docker-Content-Digest`; image config reports CUDA 13.0.2 |
| Remote model code | No Python files in the pinned repository listing; config and tokenizer have no `auto_map`. Native `NemotronHForCausalLM` and `PreTrainedTokenizerFast` are used. |

Only metadata, tokenizer configuration, weight **index** and upstream source text were downloaded for this review; no tensor files or container layers. Native vLLM/Transformers configuration handling was reviewed statically. The current model uses `layers_block_type`; the newer Transformers config provides the legacy pattern property used by vLLM. This motivated replacing the old 0.12 candidate; it is not proof that either runtime successfully loaded the model. `deploy/evon/pins.verified-2026-10-28.json` records sources and hashes. Raw local evidence is under `work/evon/pins-2026-10-28/`.

References: [pinned model configuration](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B/blob/fb9ddb6b58f2d235684388a9260671fca5ebccaf/config.json), [vLLM release](https://github.com/vllm-project/vllm/releases/tag/v0.32.0), [native Nemotron implementation](https://github.com/vllm-project/vllm/blob/v0.32.0/vllm/model_executor/models/nemotron_h.py), [native Transformers config](https://github.com/huggingface/transformers/blob/v5.16.1/src/transformers/models/nemotron_h/configuration_nemotron_h.py), [CUDA 13 driver compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html).

## Minimum GCP handoff from the owner

The easiest handoff is **an approved, prepared VM with SSH access**, not unrestricted billing/project access. Share these non-secret details:

1. Exact GCP project ID, zone and VM name; GPU type/memory, Linux distribution and architecture. Start with one A100/H100 80 GB GPU, 64 GiB+ host RAM and 150 GiB free on the Docker/model-cache filesystem. These are test-planning thresholds, not a throughput guarantee. Capacity, quota and India-region availability must be confirmed for the actual machine.
2. A working SSH command or configured host alias, using a key already stored privately on this laptop. With IAP, provide the matching `gcloud compute ssh ... --tunnel-through-iap` command. Do not paste a private SSH key, service-account JSON key, Google password or billing credentials into chat.
3. Permission to use Docker, or sudo access to install/configure the runtime if it is not already prepared. Running Docker is privileged host access; a dedicated test VM is appropriate.
4. The approved maximum duration and price ceiling, the actual machine quote, and confirmation of who can stop that exact VM. Enable a provider-side stop guard before the test. Budget alerts alone are insufficient.

For OS Login, `roles/compute.osAdminLogin` provides administrative SSH access; use ordinary OS Login only when the runtime is already prepared and that user's Docker access is arranged. Instance-level grants may also need project `compute.projects.get` for the CLI. IAP additionally needs `roles/iap.tunnelResourceAccessor`; a VM with an attached service account also requires Service Account User on that account. These roles do not themselves grant billing administration or permission to stop a VM. The owner can perform the stop, or grant narrowly scoped stop/read permissions for this VM. [OS Login requirements](https://docs.cloud.google.com/compute/docs/oslogin/set-up-oslogin), [IAP permissions](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding), [Compute permissions](https://docs.cloud.google.com/compute/docs/access/iam).

There is no need for a domain or public inference port for this initial text test. SSH forwards the loopback endpoint. Internet access is still needed on the VM to fetch the pinned image and public model after approval. If using GCP free-trial credits, GPU access requires a paid/upgraded billing account and applicable quotas; confirm credit eligibility and charges with the owner.

## Offline host and stop-plan checklist

Print requirements now without connecting anywhere:

```powershell
.\server\.venv\Scripts\python.exe scripts/evon_host_preflight.py
```

Before the actual test, copy `deploy/evon/gcp-session.example.json` into `work/evon/host-snapshot.json`. Populate only observed host values and approved session details. Read-only host commands include `uname -sm`, `nvidia-smi --query-gpu=memory.total,memory.free,driver_version --format=csv,noheader,nounits`, `docker version`, `docker compose version --short`, and checking free space on the actual Docker/cache filesystem. These commands do not prove model compatibility. Record the timestamp and exact resource identity; never mark a stop guard verified without checking it in GCP.

```powershell
.\server\.venv\Scripts\python.exe scripts/evon_host_preflight.py --snapshot work/evon/host-snapshot.json --output work/evon/host-check.json
```

The checker rejects missing/stale facts, insufficient first-GPU memory, an older driver branch, missing runtime access, and an unverified stop guard. It constructs only exact-resource inspection/stop command arrays for owner review; **it executes no command and does not verify the supplied facts independently**. Its `ready_for_gpu_acceptance` status means the reported prerequisites passed, not that the model works.

GCP supports `--max-run-duration=2h` with `--instance-termination-action=STOP` during creation or scheduling configuration. The owner must confirm the exact VM's scheduling state; changing scheduling may require the VM to be stopped. Local SSD machines also require explicit acknowledgement that local SSD contents will be discarded on automatic stop. Keep needed reports/cache on persistent storage and do not silently opt into data loss. [GCP runtime limits](https://docs.cloud.google.com/compute/docs/instances/limit-vm-runtime).

## Start the reviewed GPU service

On the GPU VM, keep the generated configuration in a private directory. Create `credentials.env` beside it, mode 0600, containing a newly generated `VLLM_API_KEY` of at least 32 characters, and `HF_TOKEN` only if access requires one. Do not paste keys into chat, commit them, place them in shell history, or use the Gnani speech key as the self-hosted server key. The Compose file uses raw environment-file parsing to preserve literal secret characters. Its entrypoint refuses an empty or short server key.

Only **after owner approval of the VM and cost** start this exact stack from that directory:

```sh
docker compose -f compose.json up -d
docker compose -f compose.json ps
```

Do not expose port 8001 publicly. Authentication protects inference routes but is not a replacement for network isolation. Open an SSH tunnel from the laptop, replacing the placeholders with the approved server login and address:

```powershell
ssh -N -L 8001:127.0.0.1:8001 USER@GPU_HOST
```

Use `http://127.0.0.1:8001/v1` as the benchmark/app base URL. Readiness is the container becoming healthy; the benchmark does not perform an unapproved warm-up request. The first measured request includes any remaining cold-start effects. With this SSH tunnel, the benchmark cannot itself tell whether the remote service is India-hosted; record the provider and region separately.

## Execute only the reviewed text flow

Keep the same flags used to create the plan. Set `EVON_BENCHMARK_API_KEY` in the current process environment through your secret manager or a hidden prompt; the script never reads `.env`. After human approval, pass the printed hash:

```powershell
.\server\.venv\Scripts\python.exe scripts/evon_benchmark.py --execute --approve-plan REVIEWED_PLAN_SHA256 --acknowledge-gpu-cost --output work/evon/result-01.json
```

Both approval arguments are required even for localhost, because the tunnel may lead to a billable GPU. The script sends sequential requests, disables reasoning traces, rejects incomplete/invalid responses, stops at the first error and never follows redirects or retries. The response stream is capped at 128 KiB; exports exclude endpoint URLs, authentication headers and upstream error bodies. Translated test text is retained for review, so use only the supplied non-sensitive corpus or equivalently consented material.

Latency is **request start → complete translation response on the laptop clock**. It includes network and server processing; it is not first-token time, speech latency, speaker playback or a calibrated quality score. Two requests are a smoke test, not a statistically useful p95. Review the first response separately from later warm requests. A failed/truncated response needs a separately reviewed rerun; do not silently increase token budgets.

After the two-case smoke test, a separately approved corpus run may assess meaning and tail latency. The next distinct gate is standard-voice STT→Evon→TTS with explicit Gnani approval. This package does not implement voice cloning or claim all-language acceptance.

## Stop and move from GCP to Yotta

Export the report, model/image pins, provider region and hardware specification. Then stop the exact Compose project:

```sh
docker compose -f compose.json down
```

This stops inference containers but **does not stop GPU VM billing**. Stop the exact temporary VM in its provider console, verify the stopped state, and check remaining disk/IP charges. Keep resource IDs recorded before launch; never stop/delete similarly named unrelated resources. Do not delete the model cache or other volumes without deciding whether they are needed.

On Yotta, reuse the same verified image/model pins and configuration, provide fresh private credentials, recreate the SSH tunnel and update the application's `EVON_BASE_URL`, `EVON_MODEL` and optional `EVON_API_KEY`. Re-run the approved acceptance cases and measure latency again; GCP timings do not establish Yotta performance. Changes to GPU architecture, runtime image, model revision or quantization require their own compatibility check. A stopped GCP GPU cannot continue serving translation while waiting for Yotta.

## Evidence and limitations

Local tests cover the offline default, exact-plan gate, limits, no retries, response validation, error redaction and portable configuration generation using fake HTTP responses. No GPU compatibility, real Evon translation, hosted model access or cloud shutdown is claimed until exercised on the selected server.

References: [Gnani model card](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B), [vLLM authentication and network guidance](https://docs.vllm.ai/en/stable/usage/security/), [GCP GPU quotas](https://docs.cloud.google.com/compute/resource-usage), [GCP trial restrictions](https://docs.cloud.google.com/free/docs/free-cloud-features).
