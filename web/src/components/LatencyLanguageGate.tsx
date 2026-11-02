import { useState } from 'react';
import { Download } from 'lucide-react';
import { latencyWorkflowReference } from '../services/latencyLanguageWorkflow';
import type {
  LatencyCaseCategory,
  LatencyGate,
  LatencyWorkflowReference,
} from '../services/latencyLanguageWorkflow';
import type { Language } from '../types/domain';
import { Badge, downloadJson } from './ui';
import './LatencyLanguageGate.css';

const ms = (value: number | null) =>
  value === null ? 'N/A' : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} ms`;
const categories: [LatencyCaseCategory, string][] = [
  ['ordinary', 'Everyday question'],
  ['negation', 'Negation and correction'],
  ['names', 'Names and associations'],
  ['numbers', 'Numbers and identifiers'],
];
function Gate({ gate, number }: { gate: LatencyGate; number: number }) {
  return (
    <article className="latency-language-direction">
      <div>
        <span className="latency-language-step">{number}</span>
        <h3>{gate.source_language === 'hi' ? 'Hindi → Tamil' : 'Tamil → Hindi'}</h3>
        <Badge tone={gate.passed ? 'neutral' : 'orange'}>
          {gate.passed ? 'Eligible for test review' : 'Physical gate pending'}
        </Badge>
      </div>
      <dl>
        <div>
          <dt>Qualifying warm captures</dt>
          <dd>
            {gate.counts.warm_qualifying} / {Math.max(10, gate.counts.warm_attempts)}
          </dd>
        </div>
        <div>
          <dt>Physical p50 / p95</dt>
          <dd>
            {ms(gate.metrics.p50_ms)} / {ms(gate.metrics.p95_ms)}
          </dd>
        </div>
        <div>
          <dt>Complete / attempted warm tests</dt>
          <dd>
            {gate.counts.warm_complete} / {gate.counts.warm_attempts}
          </dd>
        </div>
        <div>
          <dt>Failed / duplicate / overlap</dt>
          <dd>
            {gate.counts.warm_failures} / {gate.counts.duplicate_observations} /{' '}
            {gate.counts.overlap_observations}
          </dd>
        </div>
      </dl>
      <p>
        {gate.passed
          ? 'Physical timing criteria are satisfied in operator-attested records. The next test still needs fresh approval.'
          : 'Requires at least ten reviewed live warm captures, all complete, with physical p50 and p95 strictly below 2,000 ms.'}
      </p>
    </article>
  );
}

export function LatencyLanguageGate({
  plan = latencyWorkflowReference(),
  idPrefix = 'latency-language',
}: {
  plan?: LatencyWorkflowReference | null;
  idPrefix?: string;
}) {
  const [language, setLanguage] = useState<Language>('hi');
  const [category, setCategory] = useState<LatencyCaseCategory>('ordinary');
  if (plan === null)
    return (
      <section className="panel latency-language-gate">
        <h2>Ten-language expansion gate</h2>
        <p>Awaiting a validated offline plan. No provider test is authorized.</p>
      </section>
    );
  const draft = plan.draft_cases.find(
    (row) => row.source_language === language && row.category === category,
  )!;
  return (
    <section
      className="panel latency-language-gate"
      id={`${idPrefix}-gate`}
      aria-labelledby={`${idPrefix}-heading`}
    >
      <div className="panel-head">
        <div>
          <h2 id={`${idPrefix}-heading`}>Ten-language expansion gate</h2>
          <p>
            Optimize Hindi → Tamil, review the reverse direction, then propose other pairs as
            bounded tests.
          </p>
        </div>
        <Badge tone="neutral">Offline plan · 0 API calls</Badge>
      </div>
      <div className="latency-language-overview">
        <div>
          <strong>10 languages</strong>
          <span>Documented shared speech catalog</span>
        </div>
        <div>
          <strong>90 directed pairs</strong>
          <span>10 optional same-language checks</span>
        </div>
        <div>
          <strong>40 draft scripts</strong>
          <span>Fluent source review pending</span>
        </div>
      </div>
      <div className="latency-language-gates">
        <Gate gate={plan.gates.hi_to_ta} number={1} />
        <Gate gate={plan.gates.ta_to_hi} number={2} />
      </div>
      <div className="latency-language-expansion">
        <strong>3 · Other 88 directions</strong>
        <Badge tone="orange">
          {plan.full_matrix_eligible_for_test_review
            ? 'Eligible for individual test review'
            : 'Waiting for both physical gates'}
        </Badge>
        <p>
          No matrix is authorized or started here. Each proposed test needs fresh bounded approval,
          including after the gates pass. Ten language choices do not establish ten-person
          conference capacity.
        </p>
      </div>
      <p className="latency-language-boundary">
        Only live standard-voice output recorded on one shared sample clock, with reviewed meaning
        and annotations, can qualify. Synthetic decoded audio, browser rendering estimates and the
        saved provider-start timings cannot unlock these gates. Capture and provider provenance are
        operator-attested, not independently proved by this page.
      </p>
      <details>
        <summary>Review language readiness and draft test scripts</summary>
        <div className="latency-language-table">
          <table>
            <caption>
              Catalog entries prepare tests; they do not establish live language quality.
            </caption>
            <thead>
              <tr>
                <th scope="col">Language</th>
                <th scope="col">Standard voice</th>
                <th scope="col">STT / MT / TTS catalog</th>
                <th scope="col">Meaning / device review</th>
              </tr>
            </thead>
            <tbody>
              {plan.languages.map((row) => (
                <tr key={row.code}>
                  <th scope="row">{row.name}</th>
                  <td>{row.standard_voice}</td>
                  <td>Documented</td>
                  <td>Pending / pending</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="latency-language-draft-controls">
          <label className="field">
            <span>Source language</span>
            <select
              value={language}
              onChange={(event) => setLanguage(event.target.value as Language)}
            >
              {plan.languages.map((row) => (
                <option key={row.code} value={row.code}>
                  {row.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Test purpose</span>
            <select
              value={category}
              onChange={(event) => setCategory(event.target.value as LatencyCaseCategory)}
            >
              {categories.map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <article className="latency-language-draft">
          <Badge tone="orange">Draft · fluent review required</Badge>
          <p lang={language}>{draft.source_text}</p>
          <ul>
            {draft.expected_meaning.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
          <p>
            Review focus: {draft.review_focus.join(', ')}. No accepted target translation is
            supplied.
          </p>
        </article>
      </details>
      <details>
        <summary>Physical acceptance rules and plan provenance</summary>
        <ul className="latency-language-rules">
          <li>
            At least ten warm attempts in each direction; every attempt completes and qualifies.
          </li>
          <li>
            Nearest-rank p50 and p95 are each strictly under 2,000 ms. First-route observations stay
            separate.
          </li>
          <li>
            A reviewed single-channel acoustic recording, acoustic two-channel recording or
            electrical loopback uses one recording clock and reviewed sample markers.
          </li>
          <li>
            Duplicate captures, failed attempts, unreviewed meaning and overlapping output remain
            visible and prevent acceptance.
          </li>
        </ul>
        <p className="latency-language-hash">
          Source plan SHA-256: <code>{plan.source_plan_sha256}</code>
        </p>
      </details>
      <div className="latency-language-export">
        <span>Plan only · screening off · voice cloning deferred</span>
        <button
          className="button secondary"
          onClick={() => downloadJson('artha-ten-language-latency-plan.json', plan)}
        >
          <Download size={15} />
          Export offline plan
        </button>
      </div>
    </section>
  );
}
