# Charcha reviewer guide

This guide is for an invited evaluator who wants to host a meeting, admit participants and inspect Charcha. Reviewer access is granted by the project administrator; selecting a label saying “Gnani judge” is not sufficient. Charcha is an independent submission, not an official Gnani service.

**Release status:** web/API release `reviewer-reporting-20261110` was deployed and checked on 10 November 2026. Health, Reviewer/Prejoin/Usage/Performance components, configured sign-in and protected anonymous-access checks passed at 16:31:03 UTC; all 43 deployed source-file hashes matched tested code at 16:31:12 UTC, with no missing or extra files. No real invitation was issued and no authenticated live provider flow or Gnani/Modal call was made by that verification. Local desktop/mobile walkthroughs separately exercised the actual local API with mocked providers, including scoped reports. This guide does not assert that compute is running.

## 1. Receive and activate a private invitation

1. Ask the submitter for a reviewer invitation and the portal address. The administrator creates an expiring, one-use invitation from **Admin → Gnani reviewer invitations** and may bind it to your email. Invitations expire in at most seven days.
2. Sign in to Charcha with your verified email. If the invitation specifies an email, use that exact account. Keep passwords and verification codes on the sign-in page.
3. Open **Reviewer workspace**, at `/#/reviewer`, and paste the private invitation into **Activate reviewer access**. Do not put the invitation in a public URL, issue, screenshot or repository.
4. Successful redemption permits meeting creation and host admission. It does not grant administrator access. Access can expire or be revoked.

The operator can privately share `https://charcha-234398803946.asia-south2.run.app/#/reviewer` with the invitation. A working sign-in alone does not imply active reviewer permission or provider availability.

## 2. Choose the speech and translation resources

Each service can use the shared configuration or your own configuration. Shared choices appear only when your invitation permits the application's provider resources.

| Choice | What you enter | Who supplies the resources |
| --- | --- | --- |
| Shared Gnani | Nothing; the application key is never displayed | Charcha's configured Gnani account, subject to its permissions, budgets, credits and service availability |
| Your Gnani | Your Gnani speech API key | Your provider account, for recognition, synthesis and consented voice enrollment |
| Shared Evon | Nothing | Charcha's configured model service and compute account, subject to its permissions and availability |
| Your Evon | An already deployed public HTTPS OpenAI-compatible Evon base URL and exact served model name; endpoint authentication if required | Your deployed model service and its provider account |

For your Evon service:

- Deploy Evon yourself first; this page connects to its inference endpoint. It does not deploy a cloud VM or GPU from your cloud account.
- Use the HTTPS model base URL, typically `https://your-service.modal.run/v1`, and the exact model identifier your server exposes. A Gnani speech key by itself does not provision Evon compute.
- If the endpoint requires an inference bearer key, enter it in **Model API key**. For a Modal proxy-authenticated endpoint, use its **Modal-Key / Modal-Secret** pair. Do not supply a Modal CLI token, cloud account password, GCP service-account key or SSH private key.
- Modal `*.modal.run` origins are supported by default. Other public HTTPS origins require operator approval in `REVIEWER_GPU_ALLOWED_ORIGINS`. Private IPs, localhost and metadata endpoints are not supported reviewer destinations.
- When you change the endpoint, enter credentials belonging to the new endpoint. They must not follow an old address automatically.

Confirm that you are authorized to use these services, then select **Save resource choices**. Saving does not start a speech request or GPU readiness request. Credentials are held in the API process memory for the current sign-in session, not browser storage or the public repository. Responses show whether a secret is set, never its value. A process restart or session loss requires re-entry. Resource changes apply to new reviewer meetings.

Using your own providers avoids dependence on the application's provider balance. It does not remove your provider's pricing, quotas, concurrency or hardware limits. Shared resources remain subject to application controls. Resource choice never authorizes an automatic fallback to a different account's credits.

Your own providers still require the Charcha application, identity service and LiveKit media service to be running and reachable. Connecting a personal Gnani key or Evon endpoint does not bypass application hosting or make a stopped meeting server available.

## 3. Prepare translation before joining

1. In **Reviewer workspace**, name your meeting and select **Create reviewer meeting**. Keep microphones muted while preparing.
2. On Prejoin, select **Prepare translation before joining**. This is the explicit action that can wake the selected serverless model and consume GPU credits. Cold starts may take several minutes.
3. Wait for **Translation engine responded. Ready to continue.** The displayed time is an observed readiness response, not a fabricated progress percentage or an end-to-end speech benchmark.
4. The preparation hold lasts no more than **15 minutes**, and can end sooner if your session, access or room expires. Repeated clicks and status polling do not extend an active hold. Opening the page or polling readiness does not start compute.
5. Join when ready, share the invitation and admit the other signed-in participants. Set spoken/listening languages, confirm any voice-enrollment consent and start the conversation.

Connected interpreted meetings maintain their own engine hold, including between turns. New translated microphone sources wait for the engine's ready response. A prepared empty room cannot keep the shared GPU warm indefinitely. Use **Cancel preparation hold** if you abandon setup; cancellation does not terminate another occupied meeting using the same engine. Once no occupied meeting or active preparation needs an engine, Charcha releases its hold and the provider's idle timeout can scale it down. Startup and warm idle time can be billed. For your own endpoint, configure and verify its provider's scaling behavior yourself; Charcha does not own that cloud deployment. An externally managed VM must be stopped by its owner; releasing a Charcha hold does not shut down that VM.

Ready means the configured service answered the readiness check. Speech recognition, interpretation, synthesis, network transport and listener playback still need a real test. A ready model does not establish translation quality or a latency guarantee.

## 4. Run a small, reviewable test

Use separate browser profiles or devices and headphones to avoid acoustic feedback. Begin with two participants, then add languages/participants within your service capacity.

1. Say an ordinary instruction containing a number, such as “Meet in room three at four.” Inspect original and translated captions and listen to the delivered speech.
2. Correct the room to four. Confirm that a new version appears and earlier acknowledgements stay with the earlier message.
3. Have each eligible listener acknowledge the updated message. Check that the UI identifies who has acknowledged it.
4. End the meeting, inspect its saved performance data and bilingual recap, and export the recap if desired. Missing timing samples must remain marked as missing. Receiver-observed timing is distinct from physical speech-end-to-speaker playback timing.
5. Inspect VoiceShield separately if desired. It screens source audio experimentally; scores are not an identity check or an established AI-voice detection-accuracy result. Voice cloning changes synthesized output with consent and is separate from source screening.

Prepared demo fixtures are useful for reviewing interface behavior. They are not evidence of a live provider run. The [submission guide](SUBMISSION.md) and [evaluation notes](EVALUATION.md) distinguish recorded measurements, fixtures and remaining validation.

## Read the correct activity and readiness report

On **Usage**, the **Activity ledger** selector separates **My reviewer provider activity** from **Shared workspace activity**. Automatic selection prefers your personal ledger when you selected personal resources or have recorded personal-provider history. Use the selector to inspect the shared portion of a mixed setup.

- **Personal activity** contains Charcha-recorded attempted units for your signed-in account across its reviewer meetings. It does not contain another reviewer's units or silently substitute the workspace owner's ledger. Changing your resource choices does not reassign earlier activity to the new choice.
- **Shared activity** is explicitly workspace-wide, across meetings using the configured shared providers. It is not your personal provider total. If you use a personal Gnani key with shared Evon, your speech attempts appear in your personal ledger and shared translation attempts in the workspace ledger; the reverse selection splits them the other way.
- The displayed day and reset boundary use **UTC**, not the browser's local calendar. Daily units are application reservations, including failed/partial attempts and recognition connection time; they are not invoices or measured provider charges.
- **Zero** means no Charcha-recorded attempts for that resource today. It does not mean your provider account has used no credits. **Unknown** means the ledger could not be read; Charcha does not replace unavailable data with zero or another account's numbers.
- Personal activity records persist on the server by account. Deleting saved provider configuration, ending a meeting or signing out removes session credentials/resources but does not erase recorded usage history. The ledger does not store the provider secret.
- Personal provider balances, prices and remaining credits are not inferred. Use the provider dashboards for billing. Opening Usage, switching its ledger or refreshing it reads application records only; it does not start speech, synthesis or GPU compute.

The interpretation-engine panel also identifies its scope. In a current meeting, it reports that meeting's selected endpoint. Outside a current meeting, it reports your active reviewer engine, the permitted shared workspace engine, or that no engine is selected. If your meetings use multiple engines, it asks you to open a current meeting instead of inventing a combined startup time. Shared-engine meeting counts may include other workspace meetings and are labelled accordingly.

When viewing an archived Performance report, the engine panel describes current account readiness; it is not a reconstruction of the engine at the time of that saved call. Last measured startup and readiness are service-response observations, separate from translation-stage and listener-playback timings. Status polling neither starts compute nor extends a preparation hold. Use the explicit pre-meeting preparation action or an authorized occupied meeting to start the selected engine.

## 5. Finish and clear resources

Leave/end reviewer meetings and cancel any unused preparation. In Reviewer workspace, **Delete saved configuration → End meetings and delete** removes the session's resource choices and ends meetings using those reviewer resources. Sign out when done. Verify shutdown in your own provider console when using your own deployment; Charcha cannot promise that an externally hosted server has stopped billing.

The administrator can revoke an invitation or active reviewer grant from **Admin → Current invitations and access**. Do not share the privileged administrator account with reviewers.

## Operator deployment checklist

- Deploy the matching web/API release together; restart the API after server configuration changes. Keep one API worker because live rooms and reviewer secrets are memory-resident.
- Keep identity callbacks, HTTPS, LiveKit networking and persistence configured as described in [Go live](GO_LIVE.md). Reviewer access does not replace those requirements.
- For approved non-Modal inference hosts, configure exact public origins, for example `REVIEWER_GPU_ALLOWED_ORIGINS=https://evon.example.org,https://inference.example.net`. This is an operator-reviewed allowlist, not arbitrary user-controlled proxy access.
- Create private, preferably email-bound invitations with the shortest practical expiry. Grant shared-provider access only when you intend those reviews to use the configured resources.
- Confirm shared Gnani/Evon settings and the intended budget policy. Connecting reviewer-owned services does not increase the host's limits or expose its keys.
- First run the offline tests for reviewer access, credentials, routing and preparation. Then perform an authorized live test with the chosen provider account. No live provider success or current hosted availability is implied by passing offline checks.
- Do not publish invitations, keys, identity backups, billing records or private configuration. The guide belongs in GitHub; those values do not.

See [on-demand meetings](ON_DEMAND_MEETINGS.md), [architecture](ARCHITECTURE.md) and [evaluation](EVALUATION.md) for operational detail.
