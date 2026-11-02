import { useState } from 'react';
import { Download } from 'lucide-react';
import { Badge, downloadJson } from './ui';
import plan from '../data/fiveLanguagePlan.json';
import { conferenceTestPlan, MODAL_TRANSLATION_STAGE } from '../services/conferenceTestPlan';
import './Preparation.css';

const language = (code: string) =>
  plan.languages.find((entry) => entry.code === code)?.name || code;

export function FiveLanguagePlan() {
  const [routeId, setRouteId] = useState(plan.routes[0].route_id);
  const route = plan.routes.find((entry) => entry.route_id === routeId)!;
  const signInRequired = MODAL_TRANSLATION_STAGE.compute_access === 'login_required';
  return (
    <section
      className="panel preparation-panel"
      id="test-plan"
      aria-labelledby="five-language-title"
    >
      <div className="panel-head">
        <div>
          <h2 id="five-language-title">Five-language conference plan</h2>
          <p>
            Hindi, Tamil, Bengali, Telugu and Marathi. Each person speaks and listens in their
            selected language. Use the Test lab to record what a listener actually understood.
          </p>
        </div>
        <Badge tone="orange">
          {signInRequired ? 'Cloud test pending · sign-in required' : 'Five-language acceptance pending'}
        </Badge>
      </div>
      <div className="preparation-grid">
        <article>
          <Badge tone="neutral">Current five-language stage</Badge>
          <h3>${MODAL_TRANSLATION_STAGE.approved_compute_ceiling_usd} Modal compute ceiling</h3>
          <p>
            {signInRequired
              ? 'Modal sign-in needs refreshing before Evon compatibility and Hindi ↔ Tamil testing.'
              : 'Evon loaded on A100. Hindi → Tamil and Tamil → Hindi provider chains completed in separate controlled flows.'}{' '}
            {signInRequired
              ? 'This is an approved limit; account access still needs verification.'
              : 'See Saved checks for both records, including the initial Tamil STT failure and its separately approved follow-up. Meaning review, real-device calls and five-language acceptance remain pending.'}{' '}
            Actual billing is not reconciled here. The current batch permits up to ten recorded
            STT → translation → TTS flows, with no retries. Each attempt uses a separate allowance.
          </p>
        </article>
        <article>
          <Badge tone="neutral">Planned coverage</Badge>
          <h3>
            {plan.planned_directed_pairs} directions · {plan.planned_observations} observations
          </h3>
          <p>
            Two participants validate each direction. One new route and two warm repeats are
            proposed after the model loads. Five-person audio/video acceptance is a separate device
            check; these proposals are not completed results.
          </p>
        </article>
        <article>
          <Badge tone="neutral">Call experience</Badge>
          <h3>Standard voices · screening off</h3>
          <p>
            Each listener chooses a language. Camera video stays separate from translated audio.
            Start locally and use GCP hosting if deployment needs it. Voice cloning and deepfake
            experiments stay outside this stage.
          </p>
        </article>
      </div>
      <details>
        <summary>Review a direction and its everyday test phrase</summary>
        <label className="field five-language-route">
          <span>Translation direction</span>
          <select value={routeId} onChange={(event) => setRouteId(event.target.value)}>
            {plan.routes.map((entry) => (
              <option key={entry.route_id} value={entry.route_id}>
                {language(entry.source_language)} → {language(entry.target_language)}
              </option>
            ))}
          </select>
        </label>
        <p lang={route.source_language}>
          <strong>{route.source_text}</strong>
        </p>
        <ul>
          {route.expected_meaning.map((meaning) => (
            <li key={meaning}>{meaning}</li>
          ))}
        </ul>
        <p>
          Target standard voice: {route.voice.name}. Draft phrase needs a fluent source-language
          reviewer. Meaning and listener acceptance remain untested.
        </p>
        <p>
          Each proposed flow: one STT connection capped at 15 seconds including idle time, one
          translation capped at 500 source characters, and one TTS request capped at 300 characters.
          Close the flow after speaking once.
        </p>
      </details>
      <details>
        <summary>Cold starts, warm calls and measurement boundaries</summary>
        <p>
          Record queue, STT, translation and first server PCM separately from listener delay.
          Measure phrase-end to listener audio using one shared-clock recording; do not subtract two
          devices’ clocks. Missing measurements stay blank.
        </p>
        <p>
          GPU startup and model loading are separate from a newly joined route. Do not call a trial
          warm just because it ran second: record whether the model, room and output track were
          reused. Current room samples have no verified cold/warm label; use the test worksheet to
          keep those observations separate.
        </p>
        <p>
          Retain every failure and missing timing marker. Three observations per direction are
          preliminary and cannot establish reliable p95 latency. The test worksheet and setup guides
          remain in the project documentation; this page never starts a provider request.
        </p>
      </details>
      <div className="preparation-footer">
        <p>
          This is a saved test proposal. Live results appear in this page’s measurements or in
          exported observations after actual testing.
        </p>
        <button
          className="button secondary"
          onClick={() => downloadJson('artha-mesh-conference-test-plan.json', conferenceTestPlan())}
        >
          <Download size={15} /> Export conference plan
        </button>
      </div>
    </section>
  );
}
