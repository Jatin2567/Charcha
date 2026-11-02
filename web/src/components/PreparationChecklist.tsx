import { Link } from 'react-router-dom';
import { ArrowRight, Download } from 'lucide-react';
import { Badge, downloadJson } from './ui';
import './Preparation.css';

const preparationPlan = {
  schema_version: 1,
  record_type: 'pre_gpu_test_plan',
  updated: '2026-10-28',
  provider_calls: 0,
  gpu_started: false,
  voice_cloning: 'deferred',
  gates: [
    {
      id: 'local-audio',
      status: 'human_acceptance_pending',
      evidence: 'Synthetic transport checks exist; real listening results must be recorded.',
      guide: 'docs/LOCAL_TESTING.md',
    },
    {
      id: 'second-device',
      status: 'https_prepared_device_trust_and_listening_pending',
      evidence:
        'Local Docker images built and HTTPS health verified with the explicit test CA. Windows trust was deferred by the owner; second-device trust, firewall and listening remain pending.',
      guide: 'docs/TWO_DEVICE_TESTING.md',
    },
    {
      id: 'screening',
      status: 'representative_accuracy_unverified',
      evidence:
        'CPU tooling is available. Requires consented, independently labelled recordings with separate calibration/evaluation groups.',
      guide: 'evaluation/audio_screening.md',
    },
    {
      id: 'evon-text',
      status: 'gpu_and_execution_approval_pending',
      evidence:
        'Offline bounded plan available. Real output and latency require a running, approved endpoint.',
      guide: 'docs/GPU_TESTING.md',
    },
    {
      id: 'speech-translation',
      status: 'separate_flow_approval_pending',
      evidence: 'Standard voices first. GPU approval does not authorize Gnani STT/TTS requests.',
      guide: 'docs/HINDI_TAMIL_TEST.md',
    },
  ],
  note: 'Preparation status is not an automated acceptance result. Export observations separately after running tests. No model-quality or latency pass is implied.',
};

export function PreparationChecklist() {
  return (
    <section className="panel preparation-panel" aria-labelledby="preparation-title">
      <div className="panel-head">
        <div>
          <h2 id="preparation-title">Ready the tests before GPU access</h2>
          <p>
            Local work can continue while hosting is pending. These tools prepare and check the
            setup; they do not start a GPU or authorize speech requests.
          </p>
        </div>
        <Badge tone="green">Offline preparation</Badge>
      </div>
      <div className="preparation-grid">
        <article>
          <Badge tone="neutral">1 · Listen locally</Badge>
          <h3>Original speech, two people</h3>
          <p>
            Use the existing Chrome checklist below. A second device needs the separate
            secure-network setup, certificate trust on both devices and a shared network. The
            local Docker stack and short-lived certificates are prepared; Windows trust was left
            for later at your request.
          </p>
          <code>docs/TWO_DEVICE_TESTING.md</code>
        </article>
        <article>
          <Badge tone="neutral">2 · Check detection evidence</Badge>
          <h3>Recordings with known labels</h3>
          <p>
            Check consent declarations, duplicate audio and separation of speakers and sources
            before scoring. Missing recordings stay missing; generated tones are not speech-accuracy
            evidence.
          </p>
          <Link className="text-link" to="/audio-lab">
            Open Audio lab <ArrowRight size={13} />
          </Link>
        </article>
        <article>
          <Badge tone="orange">3 · GPU test later</Badge>
          <h3>Plan Hindi ↔ Tamil text first</h3>
          <p>
            Print the bounded Evon plan without contacting a server. Actual execution needs approval
            for that plan and a configured GPU endpoint. Voice cloning stays deferred.
          </p>
          <code>.\server\.venv\Scripts\python.exe scripts/evon_benchmark.py</code>
        </article>
      </div>
      <details>
        <summary>What the first GPU session should prove</summary>
        <ol>
          <li>The chosen model and serving version load and pass a readiness check.</li>
          <li>
            Two ordinary Hindi/Tamil text cases return complete translations with thinking disabled.
          </li>
          <li>
            Record request time, failures and bilingual meaning review separately. A completed
            request is not an accuracy pass.
          </li>
          <li>
            Only after separate approval, test Gnani speech input/output with standard voices.
          </li>
          <li>
            Export results and shut down the owned GPU. Repeat acceptance after moving to Yotta.
          </li>
        </ol>
      </details>
      <div className="preparation-footer">
        <p>
          No GPU result, two-device pass or detector-accuracy score has been inferred from this
          checklist.
        </p>
        <button
          className="button secondary"
          onClick={() => downloadJson('artha-mesh-pre-gpu-plan.json', preparationPlan)}
        >
          <Download size={15} />
          Export preparation plan
        </button>
      </div>
    </section>
  );
}
