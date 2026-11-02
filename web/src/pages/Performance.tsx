import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronDown,
  Download,
  FileJson,
  Gauge,
  Headphones,
  Info,
  Pause,
  Play,
  RefreshCw,
  Server,
  Settings2,
  ShieldCheck,
  Timer,
  Waves,
} from 'lucide-react';
import { Badge, ErrorNotice, PageHeading, downloadJson, downloadText } from '../components/ui';
import { useApp } from '../state/AppContext';
import { usePerformance } from '../hooks/usePerformance';
import { useTransportMetrics } from '../hooks/useTransportMetrics';
import { isLocalDemo } from '../services/api';
import {
  DEFAULT_FILTER,
  directionKey,
  filterSamples,
  measuredSamples,
  percentile,
  performanceCsv,
  sanitizedReport,
  summarize,
} from '../services/performance';
import { languageName } from '../types/domain';
import type { Language } from '../types/domain';
import type { PerformanceFilter, PerformanceSample } from '../types/performance';
import './Performance.css';
import { ColdStartComparison } from '../components/ColdStartComparison';
import { LatencyGroups } from '../components/LatencyGroups';
import { FiveLanguagePlan } from '../components/FiveLanguagePlan';
import { FiveLanguageResults } from '../components/FiveLanguageResults';
import { ReceiverAudioMetrics } from '../components/ReceiverAudioMetrics';
import { LocalRoutingEvidence } from '../components/LocalRoutingEvidence';
import { HindiTamilProviderEvidence } from '../components/HindiTamilProviderEvidence';
import { TamilHindiFollowupEvidence } from '../components/TamilHindiFollowupEvidence';
import { SpeechEndLatencyEvidence } from '../components/SpeechEndLatencyEvidence';
import { LatencyLanguageGate } from '../components/LatencyLanguageGate';
import { LaterWork } from '../components/LaterWork';

const ms = (value: number | null) =>
  value === null || !Number.isFinite(value) ? 'N/A' : `${Math.round(value).toLocaleString()} ms`;
const time = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? '—'
    : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};
const directionLabel = (source: Language, target: Language) =>
  `${languageName(source)} → ${languageName(target)}`;
const acceptance = [
  [
    'Two-way interpretation',
    'Hindi → Tamil and Tamil → Hindi. Each listener hears the chosen language, with no original-track leakage or self echo.',
  ],
  [
    'Five-language routing',
    'Check Hindi, Tamil, Bengali, Telugu and Marathi across all 20 directed paths and a same-language pair. Keep untested directions pending.',
  ],
  [
    'Video and multi-person calls',
    'Verify camera on/off, mute, rejoin and a five-person call. Each person hears the selected language without wrong-language audio, original double playback or self echo.',
  ],
  [
    'Accuracy with human review',
    'Have bilingual reviewers check meaning, names, amounts and negation against the evaluation fixtures. Set your acceptance target before scoring.',
  ],
  [
    'Latency on real speech',
    'Collect live microphone samples across each language pair. Report sample counts, p50 and p95, microphone and text input separately.',
  ],
  [
    'Recovery & device checks',
    'Test mute/unmute, language switching, reconnect, provider errors, headphones and two networks. Record the final demonstration after these pass.',
  ],
];

function StatusBadge({ sample }: { sample: PerformanceSample }) {
  return (
    <Badge
      tone={
        sample.status === 'complete' ? 'green' : sample.status === 'error' ? 'orange' : 'neutral'
      }
    >
      {sample.status === 'complete'
        ? 'Complete'
        : sample.status === 'error'
          ? `Error${sample.error_stage ? ` · ${sample.error_stage}` : ''}`
          : 'Cancelled'}
    </Badge>
  );
}
function Timeline({ samples }: { samples: PerformanceSample[] }) {
  const values = measuredSamples(samples).slice(-36);
  if (!values.length)
    return (
      <div className="performance-chart-empty">
        <Waves size={29} />
        <strong>Waiting for real measurements</strong>
        <p>
          Speak in a live room to collect timings. Scripted turns never become benchmark samples.
        </p>
      </div>
    );
  const max = Math.max(...values.map((sample) => sample.total_ms ?? 0), 1);
  return (
    <div
      className="performance-chart"
      role="img"
      aria-label={`Latest ${values.length} completed live branch latencies. Exact values are listed in the samples table.`}
    >
      <div className="performance-chart-scale">
        <span>{ms(max)}</span>
        <span>0 ms</span>
      </div>
      <div className="performance-chart-bars">
        {values.map((sample) => (
          <div
            key={sample.id}
            title={`${directionLabel(sample.source_language, sample.target_language)} · ${ms(sample.total_ms)}`}
          >
            <i style={{ height: `${Math.max(2, ((sample.total_ms ?? 0) / max) * 100)}%` }} />
          </div>
        ))}
      </div>
      <div className="performance-chart-caption">
        <span>Older</span>
        <span>Latest {values.length} live branches</span>
        <span>Newer</span>
      </div>
    </div>
  );
}

export function Performance() {
  const { membership, health, healthLoading } = useApp();
  const perf = usePerformance(membership, isLocalDemo(), healthLoading);
  const transport = useTransportMetrics(membership?.room.code, membership?.participant.id);
  const [filter, setFilter] = useState<PerformanceFilter>(DEFAULT_FILTER);
  const [manualChecks, setManualChecks] = useState<string[]>([]);
  const samples = perf.report?.samples ?? [];
  const filtered = useMemo(() => filterSamples(samples, filter), [samples, filter]);
  const summary = useMemo(() => summarize(filtered), [filtered]);
  const real = useMemo(() => measuredSamples(filtered), [filtered]);
  const directions = [...new Map(samples.map((sample) => [directionKey(sample), sample])).values()];
  const required = perf.readiness.requirements.filter((item) => item.required);
  const configured = required.filter((item) => item.configured).length;
  const mode = perf.report?.mode ?? health?.mode;
  const updateFilter = (patch: Partial<PerformanceFilter>) =>
    setFilter((current) => ({ ...current, ...patch }));
  const stages = [
    {
      key: 'queue_ms',
      label: 'Queue',
      detail: 'Utterance job waiting for its speaker’s pipeline',
      color: 'var(--chart-queue)',
    },
    {
      key: 'stt_ms',
      label: 'Speech recognition · STT',
      detail: 'Processing event received → final transcript received',
      color: 'var(--chart-speech)',
    },
    {
      key: 'mt_ms',
      label: 'Translation · MT',
      detail: 'Translation stage → text, including provider admission wait',
      color: 'var(--chart-translation)',
    },
    {
      key: 'tts_first_pcm_ms',
      label: 'Speech synthesis · TTS',
      detail:
        'Output setup + synthesis → first PCM dispatched to LiveKit; includes subscriber wait',
      color: 'var(--chart-synthesis)',
    },
  ] as const;
  const stageValues = stages.map((stage) => ({
    ...stage,
    value: percentile(
      real.map((sample) => sample[stage.key]),
      0.5,
    ),
    count: real.filter((sample) => sample[stage.key] !== null).length,
  }));
  const maxStage = Math.max(...stageValues.map((stage) => stage.value ?? 0), 1);
  return (
    <div className="performance-page">
      <PageHeading
        eyebrow="CALL QUALITY & MEASUREMENTS"
        title="Call performance."
        description="Review translation speed, receiver audio and connection health. Missing measurements stay visible."
        action={
          <button
            className="button secondary"
            onClick={() =>
              document.getElementById('readiness')?.scrollIntoView({ behavior: 'smooth' })
            }
          >
            <Settings2 size={16} />
            Setup checklist
            <ChevronDown size={14} />
          </button>
        }
      />

      <nav className="performance-section-nav" aria-label="Performance sections">
        {[
          ['Translation', 'live-latency'],
          ['Connection health', 'connection-health'],
          ['Test plan', 'test-plan'],
          ['Saved checks', 'saved-checks'],
          ['Setup', 'readiness'],
        ].map(([label, id]) => (
          <button
            key={id}
            className="button secondary"
            aria-controls={id}
            onClick={() =>
              document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
            }
          >
            {label}
          </button>
        ))}
      </nav>

      <section className="performance-scope">
        <span className="performance-scope-icon">
          <Gauge size={24} />
        </span>
        <div>
          <div className="performance-scope-top">
            <h2>
              {mode === 'live'
                ? 'Live workspace · server measurements'
                : mode === 'transport'
                  ? 'Original audio · network checks only'
                  : mode === 'demo'
                    ? 'Scripted demo · no live benchmark'
                    : 'Workspace not connected'}
            </h2>
            <Badge tone={mode === 'live' ? 'green' : 'orange'}>
              {mode === 'transport'
                ? 'Raw audio test'
                : mode === 'live'
                  ? 'Live mode'
                  : mode === 'demo'
                    ? 'Demonstration'
                    : 'Setup required'}
            </Badge>
          </div>
          <p>
            {membership ? (
              <>
                Room <strong>{membership.room.code}</strong> · Keep the call tab open while
                reviewing this page. This page never opens your microphone or joins audio.
              </>
            ) : (
              <>
                Join a room to collect conversation measurements. You can review all setup
                requirements below without any API keys.
              </>
            )}
          </p>
        </div>
      </section>
      <div className="performance-boundary">
        <Info size={16} />
        <p>
          <strong>Server timing, with a defined boundary.</strong> Total is queue-to-first-PCM plus
          a speech-recognition proxy. It does not measure speech-end-to-listener playback or certify
          a latency target. Text input skips recognition; same-language forwarding and scripted
          turns are excluded from percentiles.
        </p>
      </div>
      <ErrorNotice message={perf.error} />

      <div className="performance-controls" id="live-latency">
        <div className="performance-live-status">
          <span
            className={`status-dot ${perf.autoRefresh && perf.visible && membership && !membership.localDemo ? '' : 'performance-dot-paused'}`}
          />
          <span>
            {!perf.visible
              ? 'Refresh pauses while hidden'
              : perf.autoRefresh
                ? 'Auto refresh · every 5 seconds'
                : 'Auto refresh paused'}
          </span>
          {perf.report && (
            <small>
              Updated {time(perf.report.generated_at)}
              {perf.error ? ' · stale' : ''}
            </small>
          )}
        </div>
        <div>
          <button
            className="button secondary"
            onClick={() => perf.setAutoRefresh(!perf.autoRefresh)}
            aria-pressed={!perf.autoRefresh}
          >
            {perf.autoRefresh ? <Pause size={14} /> : <Play size={14} />}
            {perf.autoRefresh ? 'Pause' : 'Resume'}
          </button>
          <button
            className="button secondary"
            onClick={perf.refresh}
            disabled={perf.loading || healthLoading}
          >
            <RefreshCw size={14} className={perf.loading ? 'spin' : ''} />
            Refresh
          </button>
        </div>
      </div>
      <div className="performance-filters" aria-label="Performance filters">
        <label className="field">
          <span>Language pair</span>
          <select
            value={filter.direction}
            onChange={(event) => updateFilter({ direction: event.target.value })}
          >
            <option value="all">All directions</option>
            {directions.map((sample) => (
              <option key={directionKey(sample)} value={directionKey(sample)}>
                {directionLabel(sample.source_language, sample.target_language)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Input source</span>
          <select
            value={filter.input}
            onChange={(event) =>
              updateFilter({ input: event.target.value as PerformanceFilter['input'] })
            }
          >
            <option value="all">Audio & text</option>
            <option value="audio">Microphone audio</option>
            <option value="text">Typed text</option>
          </select>
        </label>
        <label className="field">
          <span>Voice mode</span>
          <select
            value={filter.voice}
            onChange={(event) =>
              updateFilter({ voice: event.target.value as PerformanceFilter['voice'] })
            }
          >
            <option value="all">All voices</option>
            <option value="standard">Standard voice</option>
            <option value="cloned">Cloned voice</option>
          </select>
        </label>
        <label className="field">
          <span>Outcome</span>
          <select
            value={filter.status}
            onChange={(event) =>
              updateFilter({ status: event.target.value as PerformanceFilter['status'] })
            }
          >
            <option value="all">All outcomes</option>
            <option value="complete">Complete</option>
            <option value="error">Error</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </label>
        <button
          className="text-link"
          onClick={() => setFilter(DEFAULT_FILTER)}
          disabled={
            filter.direction === 'all' &&
            filter.input === 'all' &&
            filter.voice === 'all' &&
            filter.status === 'all'
          }
        >
          Reset filters
        </button>
      </div>
      <div className="performance-stats">
        <article>
          <span>
            <Timer size={16} />
            Server first audio · p50
          </span>
          <strong>{ms(summary.p50_ms)}</strong>
          <small>
            {summary.live_sample_count
              ? `${summary.live_sample_count} completed live branches`
              : 'No completed live samples'}
          </small>
        </article>
        <article>
          <span>
            <Activity size={16} />
            Server first audio · p95
          </span>
          <strong>{ms(summary.p95_ms)}</strong>
          <small>Nearest-rank percentile</small>
        </article>
        <article>
          <span>
            <CheckCircle2 size={16} />
            Completed branches
          </span>
          <strong>
            {summary.success_count}
            <em> / {summary.sample_count}</em>
          </strong>
          <small>
            {summary.simulated_count} scripted · {summary.forwarded_count} forwarded
          </small>
        </article>
        <article>
          <span>
            <ShieldCheck size={16} />
            Errors / cancelled
          </span>
          <strong>
            {summary.error_count}
            <em> / {summary.cancelled_count}</em>
          </strong>
          <small>Failures remain in the record</small>
        </article>
      </div>
      <LatencyGroups samples={filtered} />
      <div className="performance-analysis-grid">
        <section className="panel performance-trend">
          <div className="panel-head">
            <h2>First-audio latency</h2>
            <Badge tone="neutral">Server boundary</Badge>
          </div>
          <p className="panel-intro">Recent completed live branches within the current filters.</p>
          <Timeline samples={filtered} />
          <div className="performance-chart-note">
            {summary.live_sample_count < 20
              ? 'Small sample caution: collect a representative set before comparing p95.'
              : 'Compare only matched devices, language pairs, input types and network conditions.'}
          </div>
        </section>
        <section className="panel performance-stage-panel">
          <div className="panel-head">
            <h2>Translation stages</h2>
            <Badge tone="neutral">Stage p50</Badge>
          </div>
          <p className="panel-intro">
            Stage medians are independent and do not add up to total p50.
          </p>
          <div className="performance-stages">
            {stageValues.map((stage) => (
              <div key={stage.key}>
                <div>
                  <strong>{stage.label}</strong>
                  <b>{ms(stage.value)}</b>
                </div>
                <div className="performance-stage-bar">
                  <i
                    style={{
                      width:
                        stage.value === null
                          ? '0%'
                          : `${Math.max(1, (stage.value / maxStage) * 100)}%`,
                      background: stage.color,
                    }}
                  />
                </div>
                <small>
                  {stage.detail} · n={stage.count}
                </small>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="panel performance-transport" id="connection-health">
        <div className="panel-head">
          <div>
            <h2>Connection health</h2>
            <p className="panel-intro">
              WebRTC diagnostics shared by the open call tab. These measure the network and audio
              transport; they are separate from translation latency.
            </p>
          </div>
          <Badge tone={transport ? 'green' : 'neutral'}>
            {transport
              ? `${transport.receiving_tracks} receiving tracks`
              : 'No current call diagnostics'}
          </Badge>
        </div>
        <div className="performance-transport-stats">
          <div>
            <span>Network round trip</span>
            <strong>{ms(transport?.network_rtt_ms ?? null)}</strong>
            <small>Selected media connection</small>
          </div>
          <div>
            <span>Audio jitter</span>
            <strong>{ms(transport?.jitter_ms ?? null)}</strong>
            <small>Mean across incoming audio tracks</small>
          </div>
          <div>
            <span>Jitter buffer</span>
            <strong>{ms(transport?.jitter_buffer_ms ?? null)}</strong>
            <small>Cumulative mean buffering delay</small>
          </div>
          <div>
            <span>Packet loss</span>
            <strong>
              {transport?.packet_loss_percent == null
                ? 'N/A'
                : `${transport.packet_loss_percent.toFixed(2)}%`}
            </strong>
            <small>
              {transport?.packets_received == null
                ? 'No received-packet statistics'
                : `${transport.packets_received.toLocaleString()} received · ${(transport.packets_lost ?? 0).toLocaleString()} lost`}
            </small>
          </div>
        </div>
        <p className="performance-export-note">
          <Info size={13} />
          {transport
            ? `Updated ${time(transport.measured_at)}. `
            : 'Keep the original call tab open. Diagnostics expire after 15 seconds without an update. '}
          These numbers do not measure when a listener hears translated speech. No audio is
          transferred to this page.
        </p>
      </section>

      <ReceiverAudioMetrics membership={membership} />

      <section className="panel performance-directions">
        <div className="panel-head">
          <h2>Language pair breakdown</h2>
          <span className="performance-small">Shared listeners count once per language branch</span>
        </div>
        {summary.by_direction.length ? (
          <div
            className="performance-table-wrap"
            tabIndex={0}
            aria-label="Scrollable language pair breakdown"
          >
            <table>
              <thead>
                <tr>
                  <th>Direction</th>
                  <th>Branches</th>
                  <th>Live timed</th>
                  <th>p50</th>
                  <th>p95</th>
                  <th>Errors</th>
                  <th>Cancelled</th>
                </tr>
              </thead>
              <tbody>
                {summary.by_direction.map((item) => (
                  <tr key={directionKey(item)}>
                    <th scope="row">
                      {directionLabel(item.source_language, item.target_language)}
                    </th>
                    <td>{item.sample_count}</td>
                    <td>{item.live_sample_count}</td>
                    <td>{ms(item.p50_ms)}</td>
                    <td>{ms(item.p95_ms)}</td>
                    <td>{item.error_count}</td>
                    <td>{item.cancelled_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="performance-table-empty">
            Language pairs appear after this room processes a turn.
          </p>
        )}
      </section>

      <section className="panel performance-samples">
        <div className="panel-head">
          <div>
            <h2>Measurement log</h2>
            <p className="panel-intro">
              {filtered.length} branches · newest first · up to{' '}
              {perf.report?.measurement.retention_limit ?? 1000} retained per room
            </p>
          </div>
          <div className="performance-export">
            <button
              className="button secondary"
              disabled={!perf.report}
              onClick={() =>
                perf.report &&
                downloadJson('artha-mesh-performance.json', sanitizedReport(perf.report, filter))
              }
            >
              <FileJson size={14} />
              JSON
            </button>
            <button
              className="button secondary"
              disabled={!perf.report}
              onClick={() =>
                perf.report &&
                downloadText('artha-mesh-performance.csv', performanceCsv(perf.report, filter))
              }
            >
              <Download size={14} />
              CSV
            </button>
          </div>
        </div>
        {filtered.length ? (
          <div
            className="performance-table-wrap"
            tabIndex={0}
            aria-label="Scrollable performance samples"
          >
            <table>
              <thead>
                <tr>
                  <th>Time / branch</th>
                  <th>Direction</th>
                  <th>Input</th>
                  <th>Voice</th>
                  <th>Outcome</th>
                  <th>Queue</th>
                  <th>STT</th>
                  <th>MT</th>
                  <th>First PCM</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {[...filtered].reverse().map((sample) => (
                  <tr key={sample.id}>
                    <td>
                      <time dateTime={sample.created_at}>{time(sample.created_at)}</time>
                      <small className="performance-sample-id">{sample.id.slice(0, 8)}</small>
                    </td>
                    <th scope="row">
                      {directionLabel(sample.source_language, sample.target_language)}
                      <small className="performance-sample-id">
                        {sample.measurement === 'simulated'
                          ? 'Scripted'
                          : sample.measurement === 'source_forwarded'
                            ? 'Source forwarded'
                            : 'Server first PCM'}
                      </small>
                    </th>
                    <td>{sample.input_kind === 'audio' ? 'Audio' : 'Text'}</td>
                    <td>{sample.voice_mode === 'cloned' ? 'Cloned' : 'Standard'}</td>
                    <td>
                      <StatusBadge sample={sample} />
                    </td>
                    <td>{ms(sample.queue_ms)}</td>
                    <td>{ms(sample.stt_ms)}</td>
                    <td>{ms(sample.mt_ms)}</td>
                    <td>{ms(sample.tts_first_pcm_ms)}</td>
                    <td>
                      <strong>{ms(sample.total_ms)}</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="performance-log-empty">
            <span>
              <Activity size={22} />
            </span>
            <div>
              <h3>
                {perf.report?.mode === 'transport'
                  ? 'No translation timings in raw audio mode.'
                  : perf.report?.mode === 'demo'
                    ? 'The demo is a walkthrough.'
                    : membership
                      ? 'Your measurements will appear here.'
                      : 'No active room in this tab.'}
              </h3>
              <p>
                {perf.report?.mode === 'transport'
                  ? 'Keep the call open to view network statistics above. Record audible listener delay separately in Test lab; a network round trip is not speech-to-listener latency.'
                  : perf.report?.mode === 'demo'
                    ? 'Scripted conversations show the experience; they do not establish model speed, quality or voice-clone performance.'
                    : membership
                      ? 'Use the call tab for live microphone speech or typed turns. This page reads measurements only.'
                      : 'Open Performance from a live call to keep the call running and share its room access with the report tab.'}
              </p>
            </div>
            {!membership && (
              <Link className="text-link" to="/">
                Start a conversation
                <ArrowRight size={14} />
              </Link>
            )}
          </div>
        )}
        <p className="performance-export-note">
          <ShieldCheck size={13} />
          Exports include filtered timing metadata only. No transcripts, participant names,
          credentials, voice references or configuration values.
        </p>
      </section>

      <section className="panel performance-definitions">
        <div className="panel-head">
          <h2>Understand the numbers</h2>
          <Info size={18} />
        </div>
        <div className="performance-definition-grid">
          <div>
            <h3>What total includes</h3>
            <p>
              Server queue → first PCM dispatch, plus the time between receiving the STT processing
              event and receiving its final transcript. The STT interval is a proxy, not measured
              speech-end latency. When that interval is missing, audio totals cover
              queue-to-first-PCM only and are partial.
            </p>
          </div>
          <div>
            <h3>What total cannot tell you</h3>
            <p>
              Microphone capture delay, client/server network travel, decoder buffering and when the
              listener actually hears speech are not measured. Receiver playback is unmeasured; no
              end-to-end claim is made.
            </p>
          </div>
          <div>
            <h3>How samples are counted</h3>
            <p>
              One utterance can produce one branch per target language. Only completed live
              synthesis branches enter p50/p95. Forwarded same-language audio, errors, cancellations
              and scripted audio are excluded.
            </p>
          </div>
          <div>
            <h3>How to compare fairly</h3>
            <p>
              Filter microphone and typed input separately. Record devices, network, languages,
              voice mode and model versions in your evaluation notes. N/A means no applicable
              measurement, never zero latency.
            </p>
          </div>
        </div>
      </section>

      <FiveLanguagePlan />

      <div id="saved-checks" className="performance-checks-anchor" aria-hidden="true" />
      <FiveLanguageResults />
      <LaterWork>
        <SpeechEndLatencyEvidence />
        <LatencyLanguageGate />
      </LaterWork>
      <HindiTamilProviderEvidence />

      <TamilHindiFollowupEvidence />

      <LocalRoutingEvidence />

      <section className="panel performance-saved-results">
        <div className="panel-head">
          <div>
            <h2>Saved local test results</h2>
            <p className="panel-intro">
              Historical transport tests stay separate from this room’s current measurements.
            </p>
          </div>
          <Badge tone="neutral">Reference evidence</Badge>
        </div>
        <details>
          <summary>Review the local cold-start audio comparison</summary>
          <ColdStartComparison />
        </details>
        <p className="performance-export-note">
          Deepfake screening and voice cloning are outside the current translation stage. The saved
          screening studies remain in Audio lab.
        </p>
        <Link className="text-link" to="/audio-lab">
          Open Audio lab →
        </Link>
      </section>

      <section className="performance-readiness" id="readiness">
        <div className="performance-section-heading">
          <div>
            <div className="eyebrow">READY FOR A REAL CONVERSATION</div>
            <h2>Your setup checklist.</h2>
            <p>
              Put credentials in the server environment. This page shows configuration presence
              only.
            </p>
          </div>
          <Badge
            tone={perf.readinessAvailable && configured === required.length ? 'green' : 'orange'}
          >
            {perf.readinessAvailable
              ? `${configured} / ${required.length} required settings present`
              : 'Reference checklist · not checked'}
          </Badge>
        </div>
        <div className="performance-boundary">
          <Server size={17} />
          <p>
            {perf.readinessAvailable ? (
              <>
                <strong>Configuration is not provider verification.</strong> A value being present
                does not establish valid credentials, account access, quota, model availability or
                India data residency. Provider connectivity has not been checked by this page.
              </>
            ) : (
              <>
                <strong>The configuration service is unavailable in this preview.</strong> All items
                below are requirements for reference. Their presence on your server has not been
                checked.
              </>
            )}
          </p>
        </div>
        <div className="performance-requirement-grid">
          {[...new Set(perf.readiness.requirements.map((item) => item.group))].map((group) => (
            <section className="panel" key={group}>
              <div className="panel-head">
                <h3>{group}</h3>
                <Settings2 size={16} />
              </div>
              <div className="performance-requirements">
                {perf.readiness.requirements
                  .filter((item) => item.group === group)
                  .map((item) => (
                    <div key={item.key}>
                      <div className="performance-requirement-top">
                        <strong>{item.label}</strong>
                        <Badge
                          tone={perf.readinessAvailable && item.configured ? 'green' : 'neutral'}
                        >
                          {perf.readinessAvailable
                            ? item.configured
                              ? 'Present'
                              : item.required
                                ? 'Required'
                                : 'Optional'
                            : item.required
                              ? 'Required · unchecked'
                              : 'Optional'}
                        </Badge>
                      </div>
                      <code>{item.key}</code>
                      <p>{item.detail}</p>
                    </div>
                  ))}
              </div>
            </section>
          ))}
        </div>
        <div className="performance-manual-grid">
          {perf.readiness.deployment_checks.map((check) => (
            <article key={check.key}>
              <span>
                <Headphones size={17} />
              </span>
              <div>
                <h3>
                  {check.label}
                  <Badge tone="neutral">Manual check</Badge>
                </h3>
                <p>{check.detail}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="panel performance-acceptance">
        <div className="panel-head">
          <div>
            <h2>Standard-voice call acceptance</h2>
            <p className="panel-intro">
              A reviewer’s checklist. Tick only after witnessing the result; these marks are
              temporary and are not automated verification.
            </p>
          </div>
          <Badge tone="neutral">
            {manualChecks.length} / {acceptance.length} reviewed
          </Badge>
        </div>
        <div>
          {acceptance.map(([label, detail]) => (
            <label key={label}>
              <input
                type="checkbox"
                checked={manualChecks.includes(label)}
                onChange={(event) =>
                  setManualChecks((current) =>
                    event.target.checked
                      ? [...current, label]
                      : current.filter((item) => item !== label),
                  )
                }
              />
              <span className="performance-check-icon" aria-hidden="true">
                {manualChecks.includes(label) && <Check size={13} />}
              </span>
              <span>
                <strong>{label}</strong>
                <small>{detail}</small>
              </span>
            </label>
          ))}
        </div>
        <p className="performance-export-note">
          <Info size={13} />
          Complete these checks with standard voices and screening off. Deepfake screening and voice
          cloning remain separate later stages.
        </p>
      </section>
      <div className="performance-reference-links">
        <span>Provider references</span>
        <a href="https://docs.gnani.ai/" target="_blank" rel="noreferrer">
          Gnani documentation
          <ArrowUpRight size={13} />
        </a>
        <a href="https://docs.livekit.io/" target="_blank" rel="noreferrer">
          LiveKit documentation
          <ArrowUpRight size={13} />
        </a>
        <a
          href="https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B"
          target="_blank"
          rel="noreferrer"
        >
          Evon model
          <ArrowUpRight size={13} />
        </a>
      </div>
    </div>
  );
}
