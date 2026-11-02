# Modal connection handoff for another AI agent

This guide is for an agent taking over Artha-Mesh's existing Modal/Evon setup. It is a connection and safety handoff, not permission to spend credits. It was prepared on 2 November 2026 from the local repository; account balance, access, deployed Apps and prices must be checked again.

## Project and boundaries

- Repository root: `C:\Users\JATIN\Documents\ChatGPT\Artha-Mesh`.
- Use PowerShell from that root. The intended local Modal CLI profile is `artha-mesh`.
- The owner completes browser sign-in. Never ask them to paste credentials, passwords, card details, API keys or tokens into chat. Do not print private config files or copy secrets into reports.
- Ask the owner to approve a concrete plan before any new billable Modal operation: state the purpose, maximum workspace usage, maximum duration, costs outside the GPU, and shutdown plan. Previous $10 and $5 authorizations were bounded historical stages, not an unlimited new grant.
- Gnani STT/TTS and other provider requests are separate from Modal and need their own applicable approval. Voice cloning remains deferred unless the owner changes that instruction.
- Do not deploy, download weights, invoke the endpoint, run a health check, generate speech, change billing, or start a paid server merely to verify a connection. Endpoint health requests can start a GPU.

## Important warning before any GPU use

After the owner's cleanup on 2 November, the allocation is **A100 80 GB in `ap` only**. Deployment and the revised reserve calculator now share `deploy/modal/allocation.json`. The calculator prices every allowed GPU and rejects missing rates or unknown selections; its H100 support is for estimating a future reviewed fallback, not authorization or runtime enablement. The runtime still accepts A100 only. The request routing region `ap-south` does not establish that inference runs in India. Review [MODAL_COST_REVIEW.md](MODAL_COST_REVIEW.md) before a paid run; older session examples and historical ceilings are not current spend approval.

## 1. Locate the local tools

The project-specific CLI is:

```powershell
Set-Location 'C:\Users\JATIN\Documents\ChatGPT\Artha-Mesh'
.\work\modal-cli-py312\.venv\Scripts\modal.exe --version
```

The pinned CLI was installed as Modal 1.6.3 with Python 3.12. If the environment is missing, inspect and run `scripts/setup_modal.ps1`: it prepares a local isolated Python/CLI environment and may download dependencies, but does not log in, deploy, allocate a GPU or call Gnani. Don't replace the project's server environment or assume a different Python minor version is compatible with the serialized deployment.

## 2. Authenticate without exposing credentials

First use the read-only checks below. If the profile is absent or its token has expired, ask the owner to complete the browser sign-in themselves. From the repository root they can run:

```powershell
.\work\modal-cli-py312\.venv\Scripts\modal.exe token new --expires-in 12h --profile artha-mesh
```

The owner should finish the browser flow and wait for the terminal to report successful verification and writing to the intended profile. The lifetime above is an example; workspace policy controls allowable lifetimes. Do not request or expose the generated token. If the workspace is wrong, stop and resolve the intended account rather than deploying elsewhere.

The Modal CLI login, the endpoint's Modal proxy credentials, and the vLLM inference key are **different credentials**. A successful CLI login does not by itself authorize or configure inference. Use the existing private credential workflow in `docs/MODAL_TESTING.md`; do not substitute the Gnani key, disable proxy authentication, make the endpoint public, or print secrets. The `work/modal-private/` directory is private and ignored; verify permissions and file presence without displaying contents. If access is missing, have the owner arrange it securely.

## 3. Read-only account and resource checks

These commands query account metadata, not model inference. Run only in the intended signed-in workspace; sanitize output before sharing because it can contain account or resource identifiers. They do not establish a current credit balance on their own in every billing configuration.

```powershell
.\work\modal-cli-py312\.venv\Scripts\modal.exe token info --profile artha-mesh
.\work\modal-cli-py312\.venv\Scripts\modal.exe billing summary --profile artha-mesh --json
.\work\modal-cli-py312\.venv\Scripts\modal.exe billing rates --profile artha-mesh --json
.\work\modal-cli-py312\.venv\Scripts\modal.exe app list --profile artha-mesh --json
.\work\modal-cli-py312\.venv\Scripts\modal.exe container list --profile artha-mesh --json
```

Confirm the workspace, applicable remaining credits and expiry, any payment method and net spend limit, a gross usage budget, and current prices with the owner/dashboard. A gross usage budget and a net out-of-pocket limit are different controls; neither proves a particular test will remain free. Billing can lag. A deployed App may have zero active containers, and an App listing alone does not prove a GPU is running. Identify containers by their App and GPU allocation; do not assume every container belongs to this project.

## 4. Understand the prepared Evon setup

- Deployment: `scripts/modal_evon.py`; runtime and safety checks: `scripts/modal_evon_runtime.py`.
- App name: `artha-evon-test`. The exact App ID can change after redeploying; identify the current deployment instead of reusing an old ID.
- Pinned model: `gnani/gnani-evon-v3.3-30B-A3B`, revision `fb9ddb6b58f2d235684388a9260671fca5ebccaf`; pins and image metadata are in `deploy/evon/`.
- A previous test reported a verified model cache in the persistent Modal volume `artha-evon-weights-v2`. Check that it still exists and is valid before planning a download; do not assume that historical evidence is current. A stopped App does not erase the volume. A later GPU cold start still has to load the model into GPU memory.
- The current service permits one GPU container and has a 300-second scale-down window. Startup, idle retention, CPU, RAM, image work, network and persistent storage may all affect costs.
- `MODAL_EVON_SESSION_EXPIRES_AT` is a reviewed absolute UTC deadline checked by the deployment code. An execution timeout or session expiry does not replace explicit App shutdown and billing reconciliation.
- The private endpoint requires Modal proxy authentication and a distinct vLLM bearer key. The inference base URL uses the exact deployed host plus `/v1`; a health request targets the host's `/health` and can start compute. Never log credentials or private redirect query strings.

## 5. Prepare a reviewable test; do not execute it yet

1. Inspect `docs/MODAL_TESTING.md` and `docs/FIVE_LANGUAGE_CALLS.md` for historical context, then check current source and live billing controls. Dated figures and completed approvals in those documents are not current account guarantees.
2. Define the exact goal, model, region, GPU type, time limit, requests, applicable current credits, gross budget, out-of-pocket limit, and whether Gnani requests are included. Include startup and possible idle time, CPU/RAM, image building, storage and other workspace usage.
3. Review the shared allocation and reserve breakdown, including an explicit allowance for costs outside serving. The live batch now requires `--modal-overhead-usd` and `--modal-workspace-ceiling-usd`, included with the resource selection in its review hash. Do not reuse a historical hash or ceiling. See [MODAL_COST_REVIEW.md](MODAL_COST_REVIEW.md).
4. `scripts/check_modal_readiness.py` without `--run` produces an offline plan. Do not send `/health` or use `--run` without an approved compute window. `scripts/evon_benchmark.py` also has an offline plan mode; see the detailed guide before use.
5. Present the concrete plan to the owner and honor their response. Do not silently retry a failed request or expand its limits.

## 6. During and after an approved session

Use the exact approved App and workspace, record timestamps and measured stages, and stop on an unexpected cost, resource, region, failure or expiry. When finished, stop **only the identified App owned by this project**. `modal app stop` changes deployment state, so do not stop unrelated Apps or delete Volumes. Confirm the App's state and check that its containers have stopped; review workspace billing again after usage data settles. A persistent volume can remain billable after the App stops. Record measured usage separately from estimates, and never promise zero bank charges based solely on a previous snapshot.

## Reference material

- Project details and historical test records: [MODAL_TESTING.md](MODAL_TESTING.md), [FIVE_LANGUAGE_CALLS.md](FIVE_LANGUAGE_CALLS.md).
- [Modal getting started and authentication](https://modal.com/docs/guide/getting-started), [token CLI](https://modal.com/docs/cli/latest/token).
- [Modal budgets and spend limits](https://modal.com/docs/guide/budgets), [pricing](https://modal.com/pricing), [billing CLI](https://modal.com/docs/cli/latest/billing).
- [Modal region selection](https://modal.com/docs/guide/region-selection), [managing deployments](https://modal.com/docs/guide/managing-deployments), [Volumes](https://modal.com/docs/guide/volumes).
