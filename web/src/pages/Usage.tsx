import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  AudioLines,
  CircleHelp,
  Clock3,
  Download,
  Gauge,
  Layers3,
  LockKeyhole,
  MicOff,
  Pause,
  Play,
  RefreshCw,
  ShieldCheck,
  Wallet,
} from 'lucide-react';
import { Badge, ErrorNotice, PageHeading, downloadJson } from '../components/ui';
import { useApp } from '../state/AppContext';
import { useUsage } from '../hooks/useUsage';
import { isLocalDemo } from '../services/api';
import { balanceSnapshotIsStale, speechFlowReferenceCost, USAGE_DEFAULTS } from '../services/usage';
import type {
  BalanceUnit,
  ProgrammePricing,
  ProviderFlow,
  UsageReport,
  UsageResource,
} from '../types/usage';
import './Usage.css';
import { SavedSpeechTests } from '../components/SavedSpeechTests';
import { FiveLanguageResults } from '../components/FiveLanguageResults';

const amount = (value: number | null) => (value === null ? 'Unknown' : value.toLocaleString());
const balanceAmount = (value: number | null, unit: BalanceUnit | null) =>
  value === null || unit === null
    ? 'Unknown'
    : unit === 'INR'
      ? `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
      : `${value.toLocaleString()} credits`;
const dateTime = (value: string | null) =>
  value
    ? new Date(value).toLocaleString([], {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        timeZoneName: 'short',
      })
    : 'Not recorded';
const flowPurpose: Record<ProviderFlow['purpose'], string> = {
  gnani_speech_check: 'Speech API check',
  voice_clone_check: 'Consented voice cloning check',
  live_interpretation: 'Live interpretation',
};
const resourceNotes: Record<UsageResource['key'], string> = {
  stt_seconds: 'Connected recognition time, including silence. Reserved in whole seconds.',
  stt_connections: 'Every attempt to open a recognition stream, including reconnections.',
  mt_requests: 'One call for each distinct translated target language.',
  mt_characters: 'Source characters reserved for each translation call.',
  tts_requests: 'One synthesis call for each distinct output voice and language branch.',
  tts_characters: 'Translated characters reserved before requesting speech.',
  voice_enrollments: 'Embedding generation attempts. Reuse an enrolled voice during the session.',
};
const statusText = {
  available: 'Available',
  warning: 'Near limit',
  exhausted: 'Stopped',
  unknown: 'Unknown usage',
};

function FlowCostReference({
  flow,
  pricing,
}: {
  flow: ProviderFlow;
  pricing: ProgrammePricing | null;
}) {
  const estimate = speechFlowReferenceCost(flow, pricing);
  return (
    <div className="usage-flow-reconciliation">
      <h3>Reference cost for reserved speech work</h3>
      <p>
        {estimate === null ? (
          <>
            <strong>Unknown.</strong>{' '}
            {flow.purpose === 'voice_clone_check'
              ? 'Enrollment and cloned-speech tariffs have not been confirmed.'
              : 'Matching recognition and synthesis pricing is not available for this flow.'}
          </>
        ) : (
          <>
            <strong>
              Approximately ₹{estimate.toLocaleString('en-IN', { maximumFractionDigits: 4 })}.
            </strong>{' '}
            Reserved recognition seconds × hourly STT rate ÷ 3,600, plus reserved synthesis
            characters × TTS rate ÷ 10,000.
          </>
        )}
      </p>
      <p>
        This is a pricing estimate, not a charge. Billing rounding is unconfirmed; provider invoices
        and failed-attempt charges may differ. It does not deduct from the reported balance.
      </p>
    </div>
  );
}

function ProviderEvidence({ report }: { report: UsageReport }) {
  const { programme, approval } = report;
  const approved = approval.status === 'approved';
  const recorded = programme.balance !== null;
  const stale = recorded && balanceSnapshotIsStale(programme.observed_at);
  return (
    <>
      <div className="usage-provider-grid">
        <section className="panel usage-programme" aria-labelledby="usage-programme-title">
          <div className="usage-section-title">
            <Wallet size={20} />
            <h2 id="usage-programme-title">Gnani account & programme</h2>
          </div>
          <div className="usage-evidence-heading">
            <div className="usage-programme-value">
              <strong>{balanceAmount(programme.balance, programme.unit)}</strong>
              <span>
                {programme.unit === 'INR'
                  ? 'Reported rupee balance'
                  : programme.unit === 'programme_credits'
                    ? 'Reported programme balance'
                    : 'Balance not connected'}
              </span>
            </div>
            <Badge>
              {programme.source === 'user_reported'
                ? 'Owner reported'
                : programme.source === 'manual_dashboard'
                  ? 'Manual dashboard snapshot'
                  : 'Unknown balance'}
            </Badge>
          </div>
          <p className="usage-intro">{programme.detail}</p>
          <p className="usage-evidence-note">
            <strong>Automatic balance sync is unavailable.</strong> This page reads the workspace
            ledger; it does not contact Gnani or deduct provider credits.
          </p>
          {recorded && (
            <p className="usage-snapshot-time">
              Recorded {dateTime(programme.observed_at)}
              {stale && <Badge tone="orange">Older than 24 hours</Badge>}
              <span>A historical snapshot, not a live account balance.</span>
            </p>
          )}
          {programme.pricing && (
            <div className="usage-rate-note">
              <h3>Speech pricing reference</h3>
              <dl className="usage-flow-meta">
                <div>
                  <dt>Recognition</dt>
                  <dd>
                    {programme.pricing.stt_per_hour === null
                      ? 'Not confirmed'
                      : `₹${programme.pricing.stt_per_hour}/hour`}
                  </dd>
                </div>
                <div>
                  <dt>Speech synthesis</dt>
                  <dd>
                    {programme.pricing.tts_per_10000_characters === null
                      ? 'Not confirmed'
                      : `₹${programme.pricing.tts_per_10000_characters}/10,000 characters`}
                  </dd>
                </div>
                <div>
                  <dt>Voice enrollment & cloning</dt>
                  <dd>Not confirmed</dd>
                </div>
              </dl>
              <p>
                From the{' '}
                <a href={programme.pricing.reference_url} target="_blank" rel="noreferrer">
                  pricing table you supplied
                </a>
                . Billing rounding and cloning coverage still need confirmation. Recognition uses
                duration; synthesis uses characters.
              </p>
            </div>
          )}
          {programme.quoted_rate && !programme.pricing && (
            <div className="usage-rate-note">
              Your quoted rate: <strong>₹{programme.quoted_rate.amount}/request</strong> · service
              coverage unconfirmed. Recognition, synthesis and cloning may have different billing
              units. No credit deduction or request allowance is calculated from this rate.
            </div>
          )}
          <p className="usage-evidence-note">
            Rupees and programme credits are separate units. Programme credits used per flow stay
            unknown until matching snapshots in programme-credit units are recorded. Rupee balance
            differences appear separately.
          </p>
        </section>

        <section className="panel usage-approval" aria-labelledby="usage-approval-title">
          <div className="usage-section-title">
            <LockKeyhole size={20} />
            <h2 id="usage-approval-title">Permission before each flow</h2>
          </div>
          <div className="usage-approval-state">
            <Badge tone={approved ? 'green' : 'neutral'}>
              {approved
                ? 'One bounded flow approved'
                : approval.status === 'disabled'
                  ? 'Transport · speech APIs disabled'
                : approval.status === 'demo'
                  ? 'Demo · no provider use'
                  : approval.status === 'unavailable'
                    ? 'Approval ledger unavailable'
                    : 'Locked · no flow approved'}
            </Badge>
          </div>
          <p className="usage-intro">{approval.detail}</p>
          {approved && (
            <dl className="usage-approval-meta">
              <div>
                <dt>Flow reference</dt>
                <dd>{approval.active_flow_id}</dd>
              </div>
              <div>
                <dt>Approval expires</dt>
                <dd>{dateTime(approval.expires_at)}</dd>
              </div>
            </dl>
          )}
          <ol className="usage-approval-steps">
            <li>Review the proposed test, endpoints, maximum work and any known billing rate.</li>
            <li>Give written permission for that single flow before it starts.</li>
            <li>The operator records its resource caps and expiry on the server.</li>
            <li>Review reservations, measured latency and dashboard balance changes afterward.</li>
          </ol>
          <p className="usage-evidence-note">
            This read-only page cannot grant permission. Another flow needs another approval;
            refreshing the page never starts a test. API keys stay on the server.
          </p>
        </section>
      </div>

      <section className="panel usage-flow-history" aria-labelledby="usage-flow-title">
        <div className="usage-flow-heading">
          <div className="usage-section-title">
            <Layers3 size={20} />
            <h2 id="usage-flow-title">Approved flow history</h2>
          </div>
          <Badge>{programme.flows.length} recorded</Badge>
        </div>
        <p className="usage-intro">
          Each flow has its own allowance in addition to the seven daily caps. Reservations show
          attempted work; provider credit charges require a separate dashboard check.
        </p>
        {programme.flows.length === 0 ? (
          <div className="usage-flow-empty">
            <LockKeyhole size={22} />
            <div>
              <h3>No provider flows recorded</h3>
              <p>No paid test history is invented in demo or offline mode.</p>
            </div>
          </div>
        ) : (
          <div className="usage-flow-list">
            {programme.flows.map((flow) => (
              <details className="usage-flow" key={flow.id}>
                <summary>
                  <div>
                    <strong>{flowPurpose[flow.purpose]}</strong>
                    <span>{dateTime(flow.started_at)}</span>
                  </div>
                  <div className="usage-flow-summary-end">
                    <Badge tone={flow.status === 'approved' ? 'green' : 'neutral'}>
                      {flow.status.charAt(0).toUpperCase() + flow.status.slice(1)}
                    </Badge>
                    <span>
                      Programme credits used: <strong>{amount(flow.credits_used)}</strong>
                    </span>
                  </div>
                </summary>
                <div className="usage-flow-body">
                  <dl className="usage-flow-meta">
                    <div>
                      <dt>Flow reference</dt>
                      <dd>{flow.id}</dd>
                    </div>
                    <div>
                      <dt>Expires</dt>
                      <dd>{dateTime(flow.expires_at)}</dd>
                    </div>
                    <div>
                      <dt>Closed</dt>
                      <dd>{dateTime(flow.closed_at)}</dd>
                    </div>
                  </dl>
                  <div className="usage-flow-table-scroll">
                    <table>
                      <caption>Reserved work within this approved flow</caption>
                      <thead>
                        <tr>
                          <th scope="col">Resource</th>
                          <th scope="col">Reserved</th>
                          <th scope="col">Flow cap</th>
                        </tr>
                      </thead>
                      <tbody>
                        {USAGE_DEFAULTS.map(({ key, label, unit }) => (
                          <tr key={key}>
                            <th scope="row">{label}</th>
                            <td>
                              {amount(flow.used[key])} {unit}
                            </td>
                            <td>{amount(flow.budgets[key])}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <FlowCostReference flow={flow} pricing={programme.pricing} />
                  <div className="usage-flow-reconciliation">
                    <h3>Measured test results</h3>
                    <dl className="usage-flow-meta">
                      {(
                        [
                          ['tts_first_pcm_ms', 'Speech first PCM', 'ms'],
                          ['tts_total_ms', 'Speech synthesis total', 'ms'],
                          ['stt_final_ms', 'Recognition final result', 'ms'],
                          ['tts_audio_seconds', 'Generated speech', 's'],
                          ['reference_seconds', 'Enrollment reference', 's'],
                        ] as const
                      ).map(([key, label, unit]) => (
                        <div key={key}>
                          <dt>{label}</dt>
                          <dd>
                            {flow.metrics[key] === undefined
                              ? 'Not measured'
                              : `${flow.metrics[key].toLocaleString(undefined, { maximumFractionDigits: 2 })} ${unit}`}
                          </dd>
                        </div>
                      ))}
                      {flow.metrics.error_stage && (
                        <div>
                          <dt>Reported error stage</dt>
                          <dd>
                            {flow.metrics.error_stage === 'none'
                              ? 'None reported'
                              : flow.metrics.error_stage}
                          </dd>
                        </div>
                      )}
                    </dl>
                    <p>
                      Timing is measured at the server. First PCM means the first generated audio
                      received by the server; it does not measure when a listener hears it.
                    </p>
                  </div>
                  <div className="usage-flow-reconciliation">
                    <h3>Account balance reconciliation</h3>
                    <dl className="usage-flow-meta">
                      <div>
                        <dt>Before</dt>
                        <dd>
                          {balanceAmount(flow.before_balance, flow.balance_unit)}
                          <small>{dateTime(flow.before_observed_at)}</small>
                        </dd>
                      </div>
                      <div>
                        <dt>After</dt>
                        <dd>
                          {balanceAmount(flow.after_balance, flow.balance_unit)}
                          <small>{dateTime(flow.after_observed_at)}</small>
                        </dd>
                      </div>
                      <div>
                        <dt>Manual dashboard delta</dt>
                        <dd>{balanceAmount(flow.balance_delta, flow.balance_unit)}</dd>
                      </div>
                    </dl>
                    <p>
                      {flow.credits_source === 'unknown'
                        ? 'Charge unknown: matching before-and-after dashboard snapshots have not been reconciled.'
                        : 'This dashboard difference includes other account activity between snapshots. It is not a provider invoice or an independently verified charge for this flow.'}
                    </p>
                  </div>
                </div>
              </details>
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function ResourceCard({ resource, reference }: { resource: UsageResource; reference: boolean }) {
  const percent = resource.utilization_percent;
  const known = resource.used !== null && percent !== null;
  return (
    <article className={`usage-resource usage-${resource.status}`}>
      <div className="usage-resource-top">
        <span>{resource.label}</span>
        <Badge
          tone={
            resource.status === 'available'
              ? 'green'
              : ['warning', 'exhausted'].includes(resource.status)
                ? 'orange'
                : 'neutral'
          }
        >
          {statusText[resource.status]}
        </Badge>
      </div>
      <div className="usage-resource-value">
        <strong>{amount(resource.used)}</strong>
        <span>{resource.unit} reserved</span>
      </div>
      {known ? (
        <div
          className="usage-progress"
          role="progressbar"
          aria-label={`${resource.label}: ${amount(resource.used)} of ${amount(resource.limit)} ${resource.unit} reserved`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.min(100, percent)}
        >
          <span style={{ width: `${Math.min(100, percent)}%` }} />
        </div>
      ) : (
        <div className="usage-progress usage-progress-unknown" aria-hidden="true" />
      )}
      <div className="usage-resource-bottom">
        <span>
          {reference ? 'Reference cap' : 'Daily cap'} <strong>{amount(resource.limit)}</strong>
        </span>
        <span>
          <strong>{amount(resource.remaining)}</strong> remaining
        </span>
      </div>
      <p>{resourceNotes[resource.key]}</p>
      {resource.limit === 0 && (
        <p className="usage-zero">A zero cap prevents new requests for this resource.</p>
      )}
    </article>
  );
}

export function Usage() {
  const { healthLoading } = useApp();
  const usage = useUsage(isLocalDemo(), healthLoading);
  const { report, available } = usage;
  const reference = !available;
  const exhausted = report.resources.filter((item) => item.status === 'exhausted');
  const warning = report.resources.filter((item) => item.status === 'warning');
  const demo = report.mode === 'demo';
  const ready = available && report.enforcement.status === 'ready';
  const reset = new Date(report.period.reset_at);

  return (
    <div className="usage-page">
      <PageHeading
        eyebrow="BUILD WITHIN YOUR BUDGET"
        title="Usage & limits"
        description="Review permission, reported account balances and bounded resource use before each live test."
        action={
          <Link className="button secondary" to="/performance">
            <Gauge size={16} />
            Performance <ArrowUpRight size={15} />
          </Link>
        }
      />

      <section
        className={`usage-scope ${exhausted.length ? 'usage-scope-stop' : ''}`}
        aria-labelledby="usage-scope-title"
      >
        <span className="usage-scope-icon">
          <ShieldCheck size={27} />
        </span>
        <div>
          <div className="usage-scope-top">
            <h2 id="usage-scope-title">
              {reference
                ? 'Reference limits · consumption unknown'
                : report.mode === 'transport'
                  ? 'Local audio · speech APIs disabled'
                : demo
                  ? 'Demo workspace · no paid inference'
                  : ready
                    ? 'Daily protection is active'
                    : 'Live requests are stopped'}
            </h2>
            <Badge tone={ready ? 'green' : reference || demo ? 'neutral' : 'orange'}>
              {reference
                ? 'Reference only'
                : report.mode === 'transport'
                  ? 'No speech inference'
                : demo
                  ? 'Demo counters'
                  : ready
                    ? 'Server enforced'
                    : 'Ledger unavailable'}
            </Badge>
          </div>
          <p>{report.enforcement.detail}</p>
          {reference && (
            <p>
              These are starter caps, not your provider allowance. Connect your backend to read its
              actual configuration.
            </p>
          )}
        </div>
      </section>

      <ErrorNotice message={usage.error} />
      {!!exhausted.length && report.mode === 'live' && (
        <div className="notice error" role="status">
          Daily cap reached: {exhausted.map((item) => item.label).join(', ')}. New work using these
          resources is blocked; ongoing completed work is not refunded.
        </div>
      )}
      {!!warning.length && (
        <div className="usage-warning-notice" role="status">
          80% warning: {warning.map((item) => item.label).join(', ')}. Finish your current test and
          check the remaining allowance.
        </div>
      )}

      <ProviderEvidence report={report} />

      <SavedSpeechTests />
      <FiveLanguageResults />

      <div className="usage-controls">
        <div className="usage-refresh-status">
          <span
            className={`status-dot ${usage.autoRefresh && usage.visible && !reference ? '' : 'usage-dot-paused'}`}
          />
          <span>
            {reference
              ? 'Read-only reference'
              : !usage.autoRefresh
                ? 'Auto refresh paused'
                : !usage.visible
                  ? 'Paused while hidden'
                  : 'Refreshes every 10 seconds'}
          </span>
          {usage.updatedAt && (
            <small>
              Updated{' '}
              {usage.updatedAt.toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
              })}
            </small>
          )}
        </div>
        <div>
          <button
            className="button secondary"
            onClick={() => usage.setAutoRefresh((value) => !value)}
            disabled={reference && !usage.error}
          >
            {usage.autoRefresh ? <Pause size={15} /> : <Play size={15} />}
            {usage.autoRefresh ? 'Pause' : 'Resume'}
          </button>
          <button
            className="button secondary"
            onClick={usage.refresh}
            disabled={healthLoading || usage.loading}
          >
            <RefreshCw size={15} className={usage.loading ? 'spin' : ''} />
            {usage.loading ? 'Refreshing…' : 'Refresh'}
          </button>
          <button
            className="button secondary"
            disabled={!available}
            onClick={() =>
              downloadJson(`artha-mesh-usage-${report.period.date}.json`, {
                ...report,
                exported_at: new Date().toISOString(),
              })
            }
          >
            <Download size={15} />
            Export
          </button>
        </div>
      </div>

      <div className="usage-period">
        <Clock3 size={16} />
        <span>
          {reference ? 'Reference daily window' : `Usage window: ${report.period.date} UTC`} ·
          resets at 00:00 UTC
          {!reference &&
            ` (${reset.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' })} locally)`}
        </span>
        <Badge>
          {available && report.enforcement.persistent
            ? 'Persistent ledger'
            : reference
              ? 'No ledger connected'
              : demo
                ? 'No provider inference'
                : 'Persistence unavailable'}
        </Badge>
      </div>

      <section className="usage-resources" aria-label="Daily resource allowances">
        {report.resources.map((resource) => (
          <ResourceCard key={resource.key} resource={resource} reference={reference} />
        ))}
      </section>

      <div className="usage-lower-grid">
        <section className="panel usage-economy" aria-labelledby="usage-economy-title">
          <div className="usage-section-title">
            <Layers3 size={20} />
            <h2 id="usage-economy-title">Make each live test count</h2>
          </div>
          <p className="usage-intro">
            Use scripted mode for UI work. Switch to live mode when you have a specific speech or
            translation check to measure.
          </p>
          <div className="usage-tip">
            <AudioLines size={19} />
            <div>
              <h3>Share work across listeners</h3>
              <p>
                One recognition stream per source speaker. Translation and speech are shared by
                matching language and voice branches; same-language microphone audio can be
                forwarded directly. When everyone uses the same language, recognition is skipped;
                forwarded audio continues, with generated live captions paused to save credits.
              </p>
            </div>
          </div>
          <div className="usage-tip">
            <MicOff size={19} />
            <div>
              <h3>Close idle streams</h3>
              <p>
                Keep the microphone muted between test cases and leave when finished. Muted speakers
                and rooms with no different-language listeners do not open a recognition stream.
                Live rooms also have a 15-minute lifetime by default.
              </p>
            </div>
          </div>
          <div className="usage-tip">
            <ShieldCheck size={19} />
            <div>
              <h3>Reuse consented voice profiles</h3>
              <p>
                Enroll once for the session. Standard voices are enough for translation checks; test
                cloning only when you need to validate the speaker’s voice.
              </p>
            </div>
          </div>
          <Link className="usage-inline-link" to="/development">
            See fixes and development decisions <ArrowUpRight size={15} />
          </Link>
        </section>

        <section className="panel usage-config" aria-labelledby="usage-config-title">
          <div className="usage-section-title">
            <Gauge size={20} />
            <h2 id="usage-config-title">Set a safe daily allowance</h2>
          </div>
          <p className="usage-intro">
            Set these fields in the server’s environment, then restart the backend. Caps apply
            across all rooms in this workspace. There is no browser reset or limit override.
          </p>
          <pre aria-label="Server usage limit environment variable names">
            {USAGE_DEFAULTS.map((item) => item.setting).join('\n')}
          </pre>
          <p>
            Start below your provider allowance. A cap of <strong>0</strong> disables new work for
            that resource. Your chosen daily caps are independent of the provider’s billing period.
          </p>
        </section>
      </div>

      <section className="panel usage-boundaries" aria-labelledby="usage-boundaries-title">
        <div className="usage-section-title">
          <CircleHelp size={20} />
          <h2 id="usage-boundaries-title">What these numbers cover</h2>
        </div>
        <div className="usage-boundary-grid">
          <div>
            <h3>Reserved work, not a bill</h3>
            <p>
              Units are reserved before provider attempts. Failed and cancelled attempts retain
              their reservation because providers may still charge. Recognition time uses
              conservative whole-second reservations. No refunds are assumed.
            </p>
          </div>
          <div>
            <h3>Daily ledger and restarts</h3>
            <p>
              Live mode requires a writable persistent ledger. Retain its data volume across
              restarts. Limits govern new requests; UTC rollover starts a new daily allowance and
              changing a cap does not undo completed calls.
            </p>
          </div>
          <div>
            <h3>Costs outside this guard</h3>
            <p>
              LiveKit room minutes and data transfer, running Evon GPU time, and use from other
              applications remain outside these counters. Set spending limits in each provider
              account and stop unused infrastructure.
            </p>
          </div>
        </div>
        <div className="usage-balance">
          <Wallet size={18} />
          <p>
            <strong>Live provider balance sync: unavailable.</strong> {report.billing.detail}{' '}
            Reading or refreshing this page does not call an AI inference endpoint.
          </p>
        </div>
      </section>
    </div>
  );
}
