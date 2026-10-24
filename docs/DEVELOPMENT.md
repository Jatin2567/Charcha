# Developer journal

The separate `/#/development` page is a manually maintained record of Track B engineering work. It describes actual observed implementation problems, their causes, the changes and the evidence available. It is not an automatically synchronized issue tracker, a conversation log, a production incident feed or a claim that real-provider acceptance is complete.

The page has status and area filters, text search, expandable notes and a filtered JSON export. All of these operate on local static data. They make **no Gnani, Evon, LiveKit or other provider requests**. The export contains the curated notes only; it does not read meeting state, audio, transcripts, enrollment data, credentials or the search text.

## Maintaining a useful record

Update `web/src/data/developerJournal.ts` when a meaningful problem is resolved, an improvement is verified, or a required acceptance check is identified. Keep entries concise and explain:

1. The behavior observed and why it matters to a speaker, listener or operator.
2. The actual root cause, without inventing an incident or an unmeasured impact.
3. The implemented change, using source paths that exist in the delivered project.
4. The check that supports the conclusion, including its limitations.
5. What remains to verify on actual accounts, devices or infrastructure.

Use `fixed` for a corrected bug, `improved` for a verified enhancement, and `pending` for unfinished work or evidence that has not been collected. Keep live acceptance pending until it has been performed. “The code is present” and “the behavior was verified with the real provider” are different claims. Do not turn a provider-double test or scripted demonstration into a translation-quality result.

The evidence labels distinguish automated checks, synthetic WebRTC, browser checks, code review and pending live checks. The synthetic RTC fixtures send generated PCM through a real local transport with provider doubles. They establish routing and transport behavior; they do not establish natural-language accuracy, clone similarity or audible end-to-end latency.

The initial entries were reviewed on **24 October 2026**. They summarize the mute-state and delayed-permission fixes, recipient routing, forwarding/resampling/playout, snapshot recovery, event authentication, timing boundaries, bounded reports and report-tab interaction. They also keep provider access, listener latency, deployment and credit-guardrail completion visible as pending evidence where applicable. This is a curated build record, not a complete chronological history of every edit.

## References and exports

The paths on each card refer to the downloadable source tree. They are displayed as text so a static published frontend does not pretend it can open private local source files. No source files are fetched by the page.

The export applies the current filters and includes `schema_version`, `record_type`, `last_updated`, scope and entries. It intentionally does not include the search query or any runtime application state. No automatic background polling or journal generation is used.

See [VALIDATION.md](VALIDATION.md) for the current validation record, [GO_LIVE.md](GO_LIVE.md) for required access and exact measurement boundaries, and [EVALUATION.md](EVALUATION.md) for the human-review workflow.
