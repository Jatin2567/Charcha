# Local Modal cost reserve preparation — 2 November 2026

This change prepares cost accounting only. No deployment, cloud health request,
account query, Gnani request or GPU invocation was made to prepare or test it.

## Current allocation and future fallbacks

`deploy/modal/allocation.json` is read by both `scripts/modal_evon.py` and the
cost calculation in `scripts/five_language_modal.py`. The current settings remain
one A100 80 GB, region `ap`, four physical CPU cores and 64 GiB RAM, with one
container maximum. Runtime validation remains A100 only. No regions or GPUs were
enabled by this change.

The calculator supports an explicit A100/H100 fallback list and all currently
listed broad/narrow Modal regions. It uses the highest hourly GPU rate in that
list and a conservative 1.75 multiplier for the full GPU + CPU + RAM allocation.
Unknown GPU/region selections and absent, nonpositive or nonfinite required
rates fail before deployment. A future H100 deployment also needs a separately
reviewed runtime update and the owner's approval.

The resource selection and allowances are included in the five-language plan
hash. Changing either requires reviewing the resulting new plan. The shared
allocation must be stable throughout a session; do not edit it concurrently
with a run.

## Reserve formula

```text
hourly = (max(allowed GPU hourly rates)
          + CPU cores × CPU core hourly rate
          + RAM GiB × memory GiB hourly rate)
         × 1.75 × maximum containers

reserve = round UP to whole US cents(
            hourly × (session seconds + 120 teardown seconds) / 3600
            + reviewed other-cost allowance)
```

The maximum session remains 30 minutes. Startup and idle time are included in
that wall-time allocation; two extra minutes are reserved for teardown. This
estimate is not a provider-enforced spending cap or proof that shutdown will
complete within that allowance.

The old automatic $0.05 allowance has been removed. The caller must explicitly
provide an allowance covering image builds, non-serving CPU work, storage,
network and any other expected costs. The owner's report of $0.73 spent without
a GPU illustrates why these costs need review; it is not a predicted upper bound
for the next build. A zero allowance is accepted only when explicitly supplied
and justified by the reviewed plan. Account-wide delayed reporting and other
concurrent jobs can exceed the estimate; verify provider controls too.

## Example figures — illustrative, not account verification

Using hourly inputs A100 $2.50, H100 $3.95, CPU $0.0473/core and RAM
$0.008/GiB, with four cores, 64 GiB, one container and a 25-minute session:

| Allowed GPUs | Serving + two-minute teardown reserve | Example other-cost allowance | Total rounded up |
| --- | ---: | ---: | ---: |
| A100 only | $2.520945 | $0.73 | $3.26 |
| A100 or H100 | $3.662820 | $0.73 | $4.40 |

These examples intentionally reserve 1.75× even for broad `ap` (currently
published at 1.15×). Neither fits a new $2.80 allowance with that example overhead.
Do not lower the overhead or multiplier merely to make a session pass the guard;
review a shorter session or a different approved plan. Confirm actual workspace
rates and included allowances before execution. Published per-second prices can
be rounded differently from billing-rate API values.

## Preparing the review

`scripts/run_five_language_calls.py` defaults to printing an offline plan. Its
new options are `--modal-overhead-usd` and `--modal-workspace-ceiling-usd`.
Values must be chosen from the actual reviewed plan, rather than copied from
these examples. Both are required to execute a live batch; neither option is
permission to do so. A default offline plan has null allowances and cannot run
live. The historical batch is one-use; do not reuse its completed output folder
or infer fresh Gnani approval from this cost change.

The workspace ceiling is a **gross cumulative monthly meter ceiling**, not a new
incremental allowance. The guard checks current metered usage plus this session's
reserve against it and rejects nonzero billed usage. It cannot exceed the legacy
runner's $5 maximum. If the owner approves incremental spend, derive and review
the cumulative ceiling from a fresh meter snapshot; do not confuse it with an
out-of-pocket limit, remaining credits or a per-flow Gnani budget.

The estimate and its inputs are saved in `compute.json` during an approved
session. Explicit App shutdown and later billing reconciliation remain required.
No budget duration was increased, and no Gnani window is opened by the calculator.

## Offline validation and sources

Tests cover both GPUs/fallback order, missing rates, nonfinite/negative values,
increased resources and container counts, duration bounds, invalid selections,
plan-hash changes, and rejection of an over-budget session before deployment or
health requests.

- [Modal pricing](https://modal.com/pricing) — checked 2 November 2026.
- [Region selection and multipliers](https://modal.com/docs/guide/region-selection).
- [Agent handoff](MODAL_AGENT_HANDOFF.md).
