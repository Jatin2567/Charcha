import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  AudioLines,
  CircleHelp,
  Clock3,
  Download,
  Gauge,
  Layers3,
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
import { USAGE_DEFAULTS } from '../services/usage';
import type { UsageResource } from '../types/usage';
import './Usage.css';

const amount = (value: number | null) => (value === null ? 'Unknown' : value.toLocaleString());
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
        description="Keep development economical. See the workspace’s daily allowances before making live calls."
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
                : demo
                  ? 'Demo workspace · no paid inference'
                  : ready
                    ? 'Daily protection is active'
                    : 'Live requests are stopped'}
            </h2>
            <Badge tone={ready ? 'green' : reference || demo ? 'neutral' : 'orange'}>
              {reference
                ? 'Reference only'
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
      {!!exhausted.length && (
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
            <strong>Provider balance: unavailable.</strong> {report.billing.detail} Reading or
            refreshing this page does not call an AI inference endpoint.
          </p>
        </div>
      </section>
    </div>
  );
}
