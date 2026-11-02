import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowRight,
  Check,
  ClipboardCheck,
  Download,
  Gauge,
  Info,
  Save,
  Server,
  Coins,
} from 'lucide-react';
import { Badge, ErrorNotice, PageHeading, downloadJson } from '../components/ui';
import { TEST_SCENARIOS, TEST_STAGES } from '../data/testLab';
import type { TestStageId } from '../data/testLab';
import { useApp } from '../state/AppContext';
import {
  browserTestStorage,
  clearObservation,
  latencyValue,
  loadObservations,
  observationKey,
  safeTestNotes,
  saveObservations,
  testLabReport,
} from '../services/testLab';
import type { TestObservation, TestOutcome } from '../services/testLab';
import { LANGUAGES } from '../types/domain';
import { batchDelivery, languageRoutingPlan } from '../services/languageCoverage';
import './TestLab.css';
import { PreparationChecklist } from '../components/PreparationChecklist';
import { FiveLanguagePlan } from '../components/FiveLanguagePlan';
import { SpeechEndLatencyEvidence } from '../components/SpeechEndLatencyEvidence';
import { LatencyLanguageGate } from '../components/LatencyLanguageGate';
import { LaterWork } from '../components/LaterWork';

const outcomeLabels: Record<TestOutcome, string> = {
  pending: 'Not tested',
  pass: 'Pass',
  fail: 'Fail',
  blocked: 'Blocked',
};

export function TestLab() {
  const { health } = useApp();
  const [params, setParams] = useSearchParams();
  const stageId: TestStageId =
    TEST_STAGES.find((entry) => entry.id === params.get('stage'))?.id || 'local-audio';
  const [selectedId, setSelectedId] = useState('greeting');
  const [observations, setObservations] = useState(() => loadObservations(browserTestStorage()));
  const [outcome, setOutcome] = useState<TestOutcome>('pending');
  const [pipeline, setPipeline] = useState('');
  const [listener, setListener] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');
  const stage = TEST_STAGES.find((entry) => entry.id === stageId)!;
  const scenarios = TEST_SCENARIOS.filter((entry) => entry.stages.includes(stageId));
  const scenario = scenarios.find((entry) => entry.id === selectedId) || scenarios[0];
  const sourceLanguages = Array.from(
    new Set(scenarios.map((entry) => entry.sourceLanguage).filter(Boolean)),
  );
  const visibleScenarios = scenario.sourceLanguage
    ? scenarios.filter((entry) => entry.sourceLanguage === scenario.sourceLanguage)
    : scenarios;
  const key = observationKey(stageId, scenario.id);
  const existing = observations[key];
  const passed = scenarios.filter(
    (entry) => observations[observationKey(stageId, entry.id)]?.outcome === 'pass',
  ).length;
  useEffect(() => {
    const entry = observations[key];
    setOutcome(entry?.outcome || 'pending');
    setPipeline(entry?.pipeline_ms == null ? '' : String(entry.pipeline_ms));
    setListener(entry?.listener_ms == null ? '' : String(entry.listener_ms));
    setNotes(entry?.notes || '');
    setSaved('');
    setError('');
    // Restore a saved observation when changing a selected test, not while editing its fields.
  }, [key]);
  const save = () => {
    try {
      const listenerMs = latencyValue(listener);
      if (listenerMs !== null && !notes.trim())
        throw new Error(
          'Describe how you observed listener delay in the notes. A network round trip is not a listener-delay measurement.',
        );
      const entry: TestObservation = {
        stage: stageId,
        scenario: scenario.id,
        outcome,
        observed_at: new Date().toISOString(),
        pipeline_ms: stage.mode === 'transport' ? null : latencyValue(pipeline),
        listener_ms: listenerMs,
        notes: safeTestNotes(notes),
      };
      const next = { ...observations, [key]: entry };
      saveObservations(browserTestStorage(), next);
      setObservations(next);
      setNotes(entry.notes);
      setError('');
      setSaved('Observation saved on this browser.');
    } catch (issue) {
      setSaved('');
      setError(issue instanceof Error ? issue.message : 'Browser storage is unavailable.');
    }
  };
  const clear = () => {
    try {
      setObservations(clearObservation(browserTestStorage(), observations, stageId, scenario.id));
      setOutcome('pending');
      setPipeline('');
      setListener('');
      setNotes('');
      setError('');
      setSaved('Saved observation cleared for this test.');
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : 'Browser storage is unavailable.');
    }
  };
  return (
    <div className="test-lab-page">
      <PageHeading
        eyebrow="ONE CLEAR STEP AT A TIME"
        title="Test lab"
        description="Check real audio, cameras and recovery first, then review translation meaning with approved speech tests."
        action={
          <button
            className="button secondary"
            onClick={() =>
              downloadJson('artha-mesh-test-observations.json', testLabReport(observations))
            }
          >
            <Download size={16} />
            Export observations
          </button>
        }
      />
      <section className="lab-intro">
        <span className="lab-intro-icon">
          <ClipboardCheck size={25} />
        </span>
        <div>
          <h2>A checklist you can hear and review</h2>
          <p>
            These scripts use everyday conversations. Select a stage, follow its setup, then record
            what you actually heard. This page never opens a microphone, approves a paid flow or
            runs a provider request.
          </p>
        </div>
        <Badge tone={health?.mode === 'transport' ? 'green' : 'neutral'}>
          {health?.mode === 'transport'
            ? 'Local raw audio'
            : health?.mode === 'live'
              ? 'Live server connected'
              : health?.mode === 'demo'
                ? 'Scripted workspace'
                : 'Server not connected'}
        </Badge>
      </section>
      <LaterWork>
        <PreparationChecklist />
        <FiveLanguagePlan />
        <SpeechEndLatencyEvidence idPrefix="testlab-speech-end" />
        <LatencyLanguageGate idPrefix="testlab-latency-language" />
      </LaterWork>
      <nav className="lab-stages" aria-label="Test stages">
        {TEST_STAGES.map((entry, index) => (
          <button
            key={entry.id}
            className={stageId === entry.id ? 'selected' : ''}
            aria-pressed={stageId === entry.id}
            onClick={() => setParams({ stage: entry.id }, { replace: true })}
          >
            <span>{String(index + 1).padStart(2, '0')}</span>
            <strong>{entry.title}</strong>
            <small>{entry.subtitle}</small>
          </button>
        ))}
      </nav>
      <section className="panel lab-setup" aria-labelledby="lab-stage-title">
        <div className="panel-head">
          <h2 id="lab-stage-title">{stage.title} · setup & acceptance</h2>
          <Badge tone={stage.mode === 'transport' ? 'green' : 'orange'}>
            {stage.mode === 'transport'
              ? 'No speech API'
              : stageId === 'cloning' || stageId === 'multi-party'
                ? 'Later stage'
                : 'Live check required'}
          </Badge>
        </div>
        <p>{stage.setup}</p>
        {stageId === 'device-check' && (
          <div className="lab-gate">
            <Info size={17} />
            <p>
              <strong>
                {health?.mode === 'live'
                  ? 'Live mode is currently configured — switch to original audio first'
                  : 'Check the mode before unmuting'}
              </strong>
              These scripts are free only in original-audio transport mode. Stop if the room shows
              live interpretation. Device results begin as Not tested; opening this checklist does
              not verify any microphone, camera or network.
            </p>
          </div>
        )}
        {stageId === 'local-audio' && (
          <div className="lab-command">
            <span>From the project folder</span>
            <code>npm run dev:local</code>
            <small>
              Keep its terminal open. This starts the local media server, API and interface.
            </small>
          </div>
        )}
        <div className="lab-gate">
          <Check size={17} />
          <p>
            <strong>Before moving on</strong>
            {stage.gate}
          </p>
        </div>
        <div className="lab-progress">
          <span>
            {passed} / {scenarios.length} manually marked passed
          </span>
          <span>Human review is still required before the next stage.</span>
        </div>
      </section>
      <div className="lab-workspace">
        <section className="lab-scenario-list" aria-labelledby="lab-scenarios-title">
          <div className="lab-list-heading">
            <span className="eyebrow">EVERYDAY TEST SCRIPTS</span>
            <h2 id="lab-scenarios-title">Choose a test</h2>
          </div>
          {scenario.sourceLanguage && (
            <label className="field lab-source-picker">
              <span>Speaker language</span>
              <select
                value={scenario.sourceLanguage}
                onChange={(event) => {
                  const first = scenarios.find(
                    (entry) => entry.sourceLanguage === event.target.value,
                  );
                  if (first) setSelectedId(first.id);
                }}
              >
                {sourceLanguages.map((code) => (
                  <option key={code} value={code}>
                    {LANGUAGES.find((l) => l.code === code)?.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {visibleScenarios.map((entry) => {
            const status = observations[observationKey(stageId, entry.id)]?.outcome || 'pending';
            return (
              <button
                key={entry.id}
                className={`lab-scenario ${scenario.id === entry.id ? 'selected' : ''}`}
                onClick={() => setSelectedId(entry.id)}
                aria-pressed={scenario.id === entry.id}
              >
                <strong>{entry.title}</strong>
                <span>{entry.focus}</span>
                <small className={`lab-outcome lab-outcome-${status}`}>
                  {outcomeLabels[status]}
                </small>
              </button>
            );
          })}
        </section>
        <section className="panel lab-detail" aria-labelledby="lab-scenario-title">
          <span className="eyebrow">{scenario.focus}</span>
          <h2 id="lab-scenario-title">{scenario.title}</h2>
          <h3>Try this conversation</h3>
          <ol className="lab-script">
            {scenario.script.map((line, index) => (
              <li key={line} lang={index === 0 ? scenario.sourceLanguage : undefined}>
                {line}
              </li>
            ))}
          </ol>
          <h3>What to listen for</h3>
          <ul className="lab-expectations">
            {scenario.expected.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="lab-reference-note">
            {stage.mode === 'transport'
              ? 'These checks use original audio. Record what the people on the devices actually heard and saw; opening this page does not establish a pass.'
              : 'These are semantic review prompts, with draft language examples. Ask a fluent reviewer to accept meaning; matching these exact words is not required.'}
          </p>
          <div className="divider" />
          <h3>Record your observation</h3>
          <p className="lab-form-intro">
            Manually entered on this browser. Saving a result does not verify a provider or
            establish an automatic benchmark. Export before switching devices or browser profiles.
          </p>
          <div className="lab-fields">
            <label className="field">
              <span>Outcome</span>
              <select
                value={outcome}
                onChange={(event) => {
                  setOutcome(event.target.value as TestOutcome);
                  setSaved('');
                }}
              >
                {Object.entries(outcomeLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Copied server pipeline (ms)</span>
              <input
                type="number"
                min="0"
                max="3600000"
                step="any"
                value={pipeline}
                placeholder="Optional"
                onChange={(event) => {
                  setPipeline(event.target.value);
                  setSaved('');
                }}
                disabled={stage.mode === 'transport'}
              />
              <small>
                {stage.mode === 'transport'
                  ? 'No STT → MT → TTS in raw audio mode.'
                  : 'Copy from Performance, if available.'}
              </small>
            </label>
            <label className="field">
              <span>Observed listener delay (ms)</span>
              <input
                type="number"
                min="0"
                max="3600000"
                step="any"
                value={listener}
                placeholder="Optional"
                onChange={(event) => {
                  setListener(event.target.value);
                  setSaved('');
                }}
              />
              <small>External observation; explain method below.</small>
            </label>
          </div>
          <label className="field lab-notes">
            <span>What happened? Include the direction and timing method.</span>
            <textarea
              maxLength={400}
              rows={4}
              value={notes}
              onChange={(event) => {
                setNotes(event.target.value);
                setSaved('');
              }}
              placeholder="For example: Hindi → Tamil. Blue was preserved; red was rejected. No duplicate audio. Listener delay not measured."
            />
            <small>
              Keep notes anonymous. Do not paste keys, credentials, private conversation content or
              audio.
            </small>
          </label>
          <ErrorNotice message={error} />
          <div className="lab-save-row">
            <button className="button primary" onClick={save}>
              <Save size={15} />
              Save observation
            </button>
            {existing && (
              <button className="button secondary" onClick={clear}>
                Clear saved observation
              </button>
            )}
            <span role="status">
              {saved ||
                (existing
                  ? `Last saved ${new Date(existing.observed_at).toLocaleString()}`
                  : 'No saved observation for this test.')}
            </span>
          </div>
        </section>
      </div>
      <details className="panel lab-language-coverage">
        <summary>Language coverage · 10 choices, 90 directed routes</summary>
        <p>
          Rows show the speaker’s language and columns show the listener’s language. Received means
          the second participant decoded audio in the five-language batch. Failed marks an attempted
          route without delivery. A dash means this batch has no result for that direction.
        </p>
        <div className="lab-matrix-wrap">
          <table aria-label="Five-language batch delivery across the language catalog">
            <thead>
              <tr>
                <th scope="col">Speaker ↓ / listener →</th>
                {LANGUAGES.map((language) => (
                  <th scope="col" key={language.code} title={language.name}>
                    {language.short}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {LANGUAGES.map((source) => (
                <tr key={source.code}>
                  <th scope="row">
                    {source.name}
                    <small>{source.native}</small>
                  </th>
                  {LANGUAGES.map((target) => (
                    <td key={target.code}>{batchDelivery(source.code, target.code)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          <strong>Fluent listening review is pending.</strong> Same-language speech forwards the
          original audio without MT/TTS. For different listener languages, the design runs one STT
          stream per active speaker, then one translation and standard-voice synthesis per distinct
          target language. Language quality, code mixing and human latency are separate checks. Odia
          is outside this shared speech-service catalog; voice cloning remains deferred.
        </p>
        <button
          className="button secondary"
          onClick={() =>
            downloadJson('artha-mesh-language-routing-plan.json', languageRoutingPlan())
          }
        >
          <Download size={15} />
          Export offline routing plan
        </button>
      </details>
      <div className="lab-measurement-note">
        <Info size={19} />
        <p>
          <strong>Keep the timing boundaries separate.</strong> Performance reports server stages
          and browser network statistics. Neither is speech-end-to-listener playback. To study
          listener delay, use a common external recording or another agreed timing method and record
          that method with the result. Two unsynchronised device clocks cannot establish it.
        </p>
      </div>
      <div className="lab-links">
        <Link to="/performance">
          <Gauge size={18} />
          <span>Performance & timings</span>
          <ArrowRight size={15} />
        </Link>
        <Link to="/usage">
          <Coins size={18} />
          <span>Usage & approved flows</span>
          <ArrowRight size={15} />
        </Link>
        <Link to="/deployment">
          <Server size={18} />
          <span>Deployment requirements</span>
          <ArrowRight size={15} />
        </Link>
      </div>
    </div>
  );
}
