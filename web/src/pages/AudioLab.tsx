import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { PhonePreview } from '../components/PhonePreview';
import {
  ArrowRight,
  AudioLines,
  Download,
  FlaskConical,
  Info,
  RefreshCw,
  ShieldQuestion,
  Timer,
  Trash2,
  Upload,
} from 'lucide-react';
import { Badge, ErrorNotice, PageHeading, downloadJson } from '../components/ui';
import {
  analyzeAudio,
  audioLabReport,
  diagnosticWav,
  getAudioLabStatus,
  inspectScreeningWav,
  recordSharedLatency,
  sharedLatencySummary,
} from '../services/audioLab';
import type {
  AudioLabStatus,
  AudioScreenResult,
  DiagnosticFixture,
  ExpectedAudioLabel,
  ScreeningObservation,
  SharedRecordingObservation,
} from '../types/audioLab';
import './AudioLab.css';
import { ScreeningLatencyComparison } from '../components/ScreeningLatencyComparison';
import { PublicSpeechScreeningResults } from '../components/PublicSpeechScreeningResults';

const milliseconds = (value: number | null | undefined) =>
  value == null || !Number.isFinite(value)
    ? 'Not measured'
    : `${Math.round(value).toLocaleString()} ms`;
const decimal = (value: number | null | undefined, suffix = '', digits = 2) =>
  value == null || !Number.isFinite(value) ? 'Unavailable' : `${value.toFixed(digits)}${suffix}`;
const verdictLabel = (result: AudioScreenResult) =>
  result.verdict === 'suspicious'
    ? 'Spoof flag · review needed'
    : result.verdict === 'allow'
      ? 'No spoof flag · not verified human'
      : 'Unknown · no reliable decision';

function ScreeningResult({ result }: { result: AudioScreenResult }) {
  return (
    <section className="panel audio-lab-result" aria-live="polite">
      <div className="panel-head">
        <h2>Screening result</h2>
        <Badge tone={result.verdict === 'suspicious' ? 'orange' : 'neutral'}>
          {verdictLabel(result)}
        </Badge>
      </div>
      <div className="audio-lab-stats">
        <div>
          <span>Detector compute</span>
          <strong>{milliseconds(result.compute_ms)}</strong>
          <small>CPU work for this analysis</small>
        </div>
        <div>
          <span>Audio examined</span>
          <strong>{milliseconds(result.analyzed_ms)}</strong>
          <small>Within {milliseconds(result.audio_window_ms)} supplied</small>
        </div>
        <div>
          <span>Model score</span>
          <strong>{result.score == null ? 'Unavailable' : decimal(result.score, '', 3)}</strong>
          <small>Uncalibrated spoof score, not accuracy</small>
        </div>
      </div>
      <div className="audio-lab-model">
        <strong>{result.model.id}</strong>
        <span>
          {result.model.kind === 'onnx_classifier'
            ? 'Local learned classifier'
            : 'Signal diagnostics only'}{' '}
          · {result.model.ready ? 'Model loaded' : 'No learned model available'}
        </span>
      </div>
      <ul className="audio-lab-reasons">
        {result.reasons.map((reason, index) => (
          <li key={`${reason}-${index}`}>{reason.replaceAll('_', ' ')}</li>
        ))}
      </ul>
      <details className="audio-lab-details">
        <summary>Signal diagnostics and model provenance</summary>
        <dl>
          <div>
            <dt>Level</dt>
            <dd>{decimal(result.diagnostics.rms_dbfs, ' dBFS')}</dd>
          </div>
          <div>
            <dt>Clipped samples</dt>
            <dd>{decimal(result.diagnostics.clipping_ratio * 100, '%')}</dd>
          </div>
          <div>
            <dt>Silence ratio</dt>
            <dd>{decimal(result.diagnostics.silence_ratio * 100, '%')}</dd>
          </div>
          <div>
            <dt>Estimated pitch</dt>
            <dd>{decimal(result.diagnostics.pitch_hz, ' Hz')}</dd>
          </div>
          <div>
            <dt>Jitter</dt>
            <dd>{decimal(result.diagnostics.jitter_percent, '%')}</dd>
          </div>
          <div>
            <dt>Shimmer</dt>
            <dd>{decimal(result.diagnostics.shimmer_percent, '%')}</dd>
          </div>
        </dl>
        <p>
          Pitch, jitter and shimmer describe this signal. Jitter and shimmer are consecutive-frame
          variation proxies, not cycle-level clinical measurements. They cannot establish whether a
          person or a generator produced it.
        </p>
        <p>
          {result.windows_analyzed} complete model windows ·{' '}
          {milliseconds(result.partial_window_ms)} incomplete tail. Unexamined trailing audio cannot
          establish a clean result.
        </p>
        <p>
          Revision: <code>{result.model.revision || 'None'}</code>
        </p>
        <p>
          SHA-256: <code>{result.model.sha256 || 'None'}</code>
        </p>
        <p>
          License: {result.model.license || 'Not applicable'} · Indian meeting-audio validation:
          pending
        </p>
      </details>
    </section>
  );
}

export function AudioLab() {
  const [status, setStatus] = useState<AudioLabStatus | null>(null);
  const [statusError, setStatusError] = useState('');
  const [statusBusy, setStatusBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [seconds, setSeconds] = useState<number | null>(null);
  const [fixture, setFixture] = useState<DiagnosticFixture | null>(null);
  const [expected, setExpected] = useState<ExpectedAudioLabel>('unlabelled');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [screening, setScreening] = useState<ScreeningObservation[]>([]);
  const [latency, setLatency] = useState<SharedRecordingObservation[]>([]);
  const [sourceEnd, setSourceEnd] = useState('');
  const [receiverStart, setReceiverStart] = useState('');
  const [duration, setDuration] = useState('');
  const [recordingId, setRecordingId] = useState('recording-1');
  const [scenario, setScenario] =
    useState<SharedRecordingObservation['scenario']>('original_audio');
  const [sharedTimebase, setSharedTimebase] = useState(false);
  const [timingError, setTimingError] = useState('');
  const [result, setResult] = useState<AudioScreenResult | null>(null);
  const mounted = useRef(true);
  const fileVersion = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    setStatusBusy(true);
    try {
      const current = await getAudioLabStatus();
      if (mounted.current) {
        setStatus(current);
        setStatusError('');
      }
    } catch (issue) {
      if (mounted.current) {
        setStatus(null);
        setStatusError(
          issue instanceof Error ? issue.message : 'Local audio service is unavailable.',
        );
      }
    } finally {
      if (mounted.current) setStatusBusy(false);
    }
  };
  useEffect(() => {
    mounted.current = true;
    void refresh();
    return () => {
      mounted.current = false;
    };
  }, []);

  const chooseFile = async (next: File | null, kind: DiagnosticFixture | null = null) => {
    const version = ++fileVersion.current;
    setFile(null);
    setSeconds(null);
    setFixture(kind);
    setConsent(false);
    setExpected('unlabelled');
    setResult(null);
    setError('');
    if (!next) return;
    try {
      if (next.size > 1_024_000)
        throw new Error('Choose a WAV smaller than 1 MB and no longer than 30 seconds.');
      const meta = inspectScreeningWav(await next.arrayBuffer());
      if (mounted.current && fileVersion.current === version) {
        setFile(next);
        setSeconds(meta.seconds);
      }
    } catch (issue) {
      if (mounted.current && fileVersion.current === version)
        setError(issue instanceof Error ? issue.message : 'The audio file could not be read.');
    }
  };
  const generate = (kind: DiagnosticFixture) => {
    if (fileInput.current) fileInput.current.value = '';
    void chooseFile(
      new File([diagnosticWav(kind)], `${kind}-diagnostic.wav`, { type: 'audio/wav' }),
      kind,
    );
  };
  const run = async () => {
    if (!file || busy) return;
    setBusy(true);
    setError('');
    const input = file,
      expectedLabel = expected,
      diagnostic = fixture;
    try {
      const response = await analyzeAudio(input, consent);
      if (mounted.current) {
        setResult(response.result);
        setScreening((rows) => [
          ...rows.slice(-49),
          {
            id: crypto.randomUUID(),
            observed_at: new Date().toISOString(),
            expected_label: diagnostic ? 'unlabelled' : expectedLabel,
            diagnostic_fixture: diagnostic,
            result: response.result,
          },
        ]);
      }
    } catch (issue) {
      if (mounted.current)
        setError(issue instanceof Error ? issue.message : 'Local analysis failed.');
    } finally {
      if (mounted.current) setBusy(false);
    }
  };
  const saveTiming = () => {
    try {
      if (!sharedTimebase)
        throw new Error(
          'Confirm that both positions come from one recording with a shared timeline.',
        );
      const row = recordSharedLatency(sourceEnd, receiverStart, scenario, recordingId, duration);
      setLatency((rows) => [...rows.slice(-99), row]);
      setTimingError('');
    } catch (issue) {
      setTimingError(issue instanceof Error ? issue.message : 'Check the recording positions.');
    }
  };
  const summary = sharedLatencySummary(latency, scenario);
  const newestTiming = latency.at(-1);

  return (
    <div className="audio-lab-page">
      <PageHeading
        eyebrow="LOCAL AUDIO EVIDENCE"
        title="Audio lab."
        description="Inspect a recording, test screening behavior and keep timing boundaries explicit."
        action={
          <button
            className="button secondary"
            disabled={!screening.length && !latency.length}
            onClick={() =>
              downloadJson('charcha-local-audio-report.json', audioLabReport(screening, latency))
            }
          >
            <Download size={16} />
            Export report
          </button>
        }
      />
      <section className="audio-lab-intro">
        <span className="audio-lab-icon">
          <FlaskConical size={27} />
        </span>
        <div>
          <h2>Local experiments, honest outcomes</h2>
          <p>
            Compare original speech with a phone-line preview in your browser, or review prior
            screening and timing measurements. Reports stay in this tab until you export them.
          </p>
          <button className="button secondary" onClick={() => fileInput.current?.focus()}>
            Choose audio for the 8 kHz preview
          </button>
        </div>
        <Badge tone="neutral">Experimental</Badge>
      </section>
      <ScreeningLatencyComparison />
      <PublicSpeechScreeningResults />
      <section className="audio-lab-status panel">
        <div className="panel-head">
          <h2>Screening service</h2>
          <button
            className="button secondary"
            disabled={statusBusy || busy}
            onClick={() => void refresh()}
          >
            <RefreshCw size={14} className={statusBusy ? 'spin' : ''} />
            Refresh
          </button>
        </div>
        <ErrorNotice message={statusError} />
        {status ? (
          <div className="audio-lab-status-grid">
            <div>
              <span>Local analysis</span>
              <strong>{status.enabled ? 'Available' : 'Disabled'}</strong>
            </div>
            <div>
              <span>Room screening policy</span>
              <strong>
                {status.mode === 'monitor'
                  ? 'Monitor · report only'
                  : status.mode === 'enforce'
                    ? 'Enforce · holds audio'
                    : 'Off'}
              </strong>
            </div>
            <div>
              <span>Learned model</span>
              <strong>{status.model.ready ? 'Loaded on CPU' : 'Unavailable'}</strong>
            </div>
            <div>
              <span>Provider requests</span>
              <strong>0</strong>
            </div>
          </div>
        ) : (
          <p className="muted">
            Start the local workspace to enable analysis. This page does not connect to a model
            provider.
          </p>
        )}
        <p className="audio-lab-note">
          A 4.04-second model window adds a collection delay before a verdict. Detector compute time
          is separate. Monitoring does not block audio; enforcement can add the window delay to the
          call.
        </p>
      </section>
      <div className="audio-lab-grid">
        <section className="panel audio-lab-upload">
          <div className="panel-head">
            <h2>1. Choose a recording</h2>
            <Upload size={19} />
          </div>
          <p className="muted">
            Mono · 16 kHz · 16-bit PCM WAV · up to 30 seconds. Use at least 4.04 seconds of speech
            for the learned model. No automatic upload.
          </p>
          <label className="field">
            <span>Recording file</span>
            <input
              ref={fileInput}
              type="file"
              accept=".wav,audio/wav,audio/x-wav"
              disabled={busy}
              onChange={(event) => void chooseFile(event.target.files?.[0] ?? null)}
            />
          </label>
          {file && (
            <p className="audio-lab-file">
              <AudioLines size={17} />
              <span>
                {file.name}
                <small>{decimal(seconds, ' seconds')} · held in this tab until analysis</small>
              </span>
            </p>
          )}
          {file && <PhonePreview file={file} />}
          <label className="field">
            <span>Known source label</span>
            <select
              value={expected}
              disabled={busy || !!fixture}
              onChange={(event) => setExpected(event.target.value as ExpectedAudioLabel)}
            >
              <option value="unlabelled">Unknown / not independently labelled</option>
              <option value="human">Human speech · known recording source</option>
              <option value="synthetic">Synthetic speech · known generator source</option>
            </select>
            <small>
              This is your annotation, not a detector finding. Diagnostic tones are excluded from
              speech-quality evidence.
            </small>
          </label>
          <label className="audio-lab-checkbox">
            <input
              type="checkbox"
              checked={consent}
              disabled={busy || !file}
              onChange={(event) => setConsent(event.target.checked)}
            />
            <span>
              I have permission to process this recording on the local server. Audio is not saved by
              this analysis endpoint.
            </span>
          </label>
          <ErrorNotice message={error} />
          <button
            className="button primary"
            onClick={() => void run()}
            disabled={!status?.enabled || !file || !consent || busy}
          >
            <FlaskConical size={16} />
            {busy ? 'Analyzing locally…' : 'Analyze locally'}
          </button>
          <div className="audio-lab-fixtures">
            <strong>Or generate a diagnostic fixture</strong>
            <p>
              Five-second signals created in your browser. They test silence/clipping handling, not
              deepfake accuracy. Nothing plays automatically.
            </p>
            <div>
              {(['silence', 'tone', 'clipping'] as const).map((kind) => (
                <button
                  key={kind}
                  className="button secondary"
                  disabled={busy}
                  onClick={() => generate(kind)}
                >
                  {kind === 'silence'
                    ? 'Silence'
                    : kind === 'tone'
                      ? 'Steady tone'
                      : 'Clipped signal'}
                </button>
              ))}
            </div>
            {fixture && <Badge tone="orange">Diagnostic fixture · {fixture}</Badge>}
          </div>
        </section>
        {result ? (
          <ScreeningResult result={result} />
        ) : (
          <section className="panel audio-lab-empty">
            <ShieldQuestion size={39} />
            <h2>No analysis yet</h2>
            <p>
              An unknown result stays unknown. A low spoof score does not verify identity, liveness
              or consent.
            </p>
            <p>
              The classifier needs held-out Indian-language, noisy-speech and unseen-generator
              evaluation before its thresholds can be trusted.
            </p>
          </section>
        )}
      </div>
      <section className="panel audio-lab-timing">
        <div className="panel-head">
          <h2>2. Annotate a shared recording</h2>
          <Badge tone="neutral">Manual listener measurement</Badge>
        </div>
        <p className="muted">
          Record the source and receiver into one synchronized, consented recording, ideally on
          separate channels. For original audio, compare the same short marker’s onset at source and
          receiver. For translation, compare source phrase-end with first translated audio. Separate
          device clocks, network RTT and server first-PCM timings cannot substitute for this
          measurement.
        </p>
        <div className="audio-lab-timing-fields">
          <label className="field">
            <span>Test scenario</span>
            <select
              value={scenario}
              onChange={(event) =>
                setScenario(event.target.value as SharedRecordingObservation['scenario'])
              }
            >
              <option value="original_audio">Original audio · no provider credits</option>
              <option value="standard_translation">
                Standard translation · later approved test
              </option>
            </select>
          </label>
          <label className="field">
            <span>Anonymous recording ID</span>
            <input
              value={recordingId}
              maxLength={48}
              onChange={(event) => setRecordingId(event.target.value)}
              placeholder="recording-1"
            />
            <small>Use a reference code, not a personal filename.</small>
          </label>
          <label className="field">
            <span>Recording duration · seconds</span>
            <input
              type="number"
              min="0"
              max="86400"
              step="0.001"
              value={duration}
              onChange={(event) => setDuration(event.target.value)}
              placeholder="30.000"
            />
          </label>
          <label className="field">
            <span>
              {scenario === 'original_audio' ? 'Source marker starts' : 'Source phrase ends'} ·
              seconds
            </span>
            <input
              type="number"
              min="0"
              max="86400"
              step="0.001"
              value={sourceEnd}
              onChange={(event) => setSourceEnd(event.target.value)}
              placeholder="4.250"
            />
          </label>
          <label className="field">
            <span>Received audio starts · seconds</span>
            <input
              type="number"
              min="0"
              max="86400"
              step="0.001"
              value={receiverStart}
              onChange={(event) => setReceiverStart(event.target.value)}
              placeholder="4.680"
            />
          </label>
        </div>
        <label className="audio-lab-checkbox">
          <input
            type="checkbox"
            checked={sharedTimebase}
            onChange={(event) => setSharedTimebase(event.target.checked)}
          />
          <span>
            Both positions are observations from the same recording and timeline. This does not
            start a call or run translation.
          </span>
        </label>
        <ErrorNotice message={timingError} />
        <div className="audio-lab-actions">
          <button className="button secondary" onClick={saveTiming}>
            <Timer size={16} />
            Add observation
          </button>
          {newestTiming && (
            <span role="status">
              Last added: {milliseconds(newestTiming.delay_ms)} · manually annotated
            </span>
          )}
        </div>
        <div className="audio-lab-stats">
          <div>
            <span>Selected scenario</span>
            <strong>{summary.count} observations</strong>
            <small>Original and translated audio stay separate</small>
          </div>
          <div>
            <span>Typical · p50</span>
            <strong>{milliseconds(summary.p50_ms)}</strong>
            <small>Manual shared-recording samples</small>
          </div>
          <div>
            <span>Tail · p95</span>
            <strong>{milliseconds(summary.p95_ms)}</strong>
            <small>
              {summary.count < 20
                ? 'Small sample: collect more before comparing'
                : 'Nearest-rank percentile'}
            </small>
          </div>
        </div>
        {latency.length > 0 && (
          <div className="audio-lab-table-wrap">
            <table>
              <caption>Recent manual observations</caption>
              <thead>
                <tr>
                  <th>Recording</th>
                  <th>Scenario</th>
                  <th>Source event</th>
                  <th>Receiver start</th>
                  <th>Delay</th>
                </tr>
              </thead>
              <tbody>
                {latency
                  .slice(-8)
                  .reverse()
                  .map((row) => (
                    <tr key={row.id}>
                      <td>{row.recording_id}</td>
                      <td>
                        {row.scenario === 'original_audio' ? 'Original marker' : 'Phrase end'}
                      </td>
                      <td>{milliseconds(row.source_event_ms)}</td>
                      <td>{milliseconds(row.receiver_start_ms)}</td>
                      <td>{milliseconds(row.delay_ms)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="panel audio-lab-next">
        <div>
          <h2>Continue the two-browser test</h2>
          <p>
            Keep two Chrome profiles in the local room, use headphones and begin with microphones
            off. Check greetings, names, numbers, quiet speech and mute/unmute. Record wrong routing
            and missing audio as failures. Translation and voice cloning remain separate later
            tests.
          </p>
        </div>
        <Link className="button secondary" to="/tests">
          Open Test lab
          <ArrowRight size={15} />
        </Link>
        <Link className="button secondary" to="/performance">
          View performance
          <ArrowRight size={15} />
        </Link>
      </section>
      <div className="audio-lab-footer">
        <p>
          <Info size={15} />
          Up to 50 screening results and 100 timing observations are kept in tab memory. Exports
          omit audio and filenames.
        </p>
        <button
          className="text-link"
          disabled={busy || (!screening.length && !latency.length && !file)}
          onClick={() => {
            setScreening([]);
            setLatency([]);
            setResult(null);
            void chooseFile(null);
            if (fileInput.current) fileInput.current.value = '';
          }}
        >
          <Trash2 size={14} />
          Clear this session
        </button>
      </div>
    </div>
  );
}
