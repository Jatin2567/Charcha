import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  ExternalLink,
  ShieldCheck,
  CheckCircle2,
  Clock,
  Cpu,
  Layers,
  FileCheck2,
  Gauge,
  Sparkles,
  Heart,
  Headphones,
} from 'lucide-react';
import { Badge } from '../components/ui';
import './Impact.css';

export function Impact() {
  return (
    <div className="impact-page">
      <header className="impact-hero">
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
          <Badge tone="green">Elite Systems &amp; Voice AI Submission</Badge>
          <Badge tone="neutral">The Great Indian AI Internship Challenge · Gnani.ai</Badge>
        </div>
        <h1>ARTHA-MESH</h1>
        <p className="impact-subtitle">
          Bridging India&apos;s languages with empathy, verifiable precision, and sovereign security. Built to empower inter-state commerce, emergency coordination, and everyday conversations without losing the human voice.
        </p>
      </header>

      {/* EXECUTIVE LIVE HUD BOX */}
      <div className="executive-preview-hud" aria-label="Live System Coordination HUD">
        <div className="hud-header">
          <span>Live Indic Telephony &amp; WebRTC Gateway HUD</span>
          <Badge tone="green">Streaming Active · 1.56s Median</Badge>
        </div>
        <div className="hud-dialogue">
          <div className="hud-turn">
            <span className="hud-meta">Spoken Hindi Input (Gnani Prisma STT)</span>
            <div className="hud-text">&ldquo;हमें 1976 यूनिट नहीं चाहिए, सिर्फ 200 यूनिट भेजो।&rdquo;</div>
          </div>
          <div className="hud-turn">
            <span className="hud-meta">Synthesized Tamil Output (Evon v3.3 Clause Stream &rarr; Timbre TTS &middot; 1.56s Stage)</span>
            <div className="hud-text">&ldquo;எங்களுக்கு 1976 அலகுகள் தேவையில்லை, 200 அலகுகளை மட்டும் அனுப்பவும்.&rdquo;</div>
          </div>
        </div>
        <div className="hud-tags">
          <div className="hud-tag">
            <Clock size={15} />
            <span><strong>1.56s</strong> Median Server Stage Latency</span>
          </div>
          <div className="hud-tag">
            <FileCheck2 size={15} />
            <span><strong>Dual Captions</strong> + Entity Tagging (1976, 200, नहीं/not)</span>
          </div>
          <div className="hud-tag">
            <Headphones size={15} />
            <span><strong>VoiceShield</strong> Waveform Tracking + Auditory Check</span>
          </div>
          <div className="hud-tag">
            <CheckCircle2 size={15} />
            <span><strong>SHA-256</strong> Verifiable Session Audit Hash</span>
          </div>
        </div>
      </div>

      {/* THE HUMAN PERSPECTIVE */}
      <section className="impact-section" aria-labelledby="human-heading">
        <h2 id="human-heading">
          <Heart size={22} style={{ color: '#e11d48' }} />
          The Human Reality: Language is Livelihood, Respect &amp; Mutual Trust
        </h2>
        <div className="human-narrative-card">
          <p>
            India is a subcontinent of 1.4 billion people and 22 official languages, where inter-state commerce, agricultural supply chains, emergency handovers, and personal conversations cross linguistic borders every single minute.
          </p>
          <div className="human-narrative-grid">
            <div className="narrative-point">
              <strong>The Dignity of Speaking Your Mother Tongue</strong>
              <p>
                When a Surat textile weaver speaks to a distributor in Madurai, forced English or broken phrases create hesitation and unequal ground. Speaking your native language is an act of dignity, confidence, and mutual respect.
              </p>
            </div>
            <div className="narrative-point">
              <strong>Why Precision Matters to Real Livelihoods</strong>
              <p>
                A dropped negation (translating <em>&ldquo;nahi bhejna&rdquo;</em> as <em>&ldquo;send&rdquo;</em>) or a misheard batch number (1976 vs 1972) isn&apos;t a minor benchmark glitch — it can cost a small business their working capital and ruin a multi-year supplier partnership.
              </p>
            </div>
            <div className="narrative-point">
              <strong>Protecting Families from Synthetic Impersonation</strong>
              <p>
                As generative deepfake scams exploit degraded cellular phone calls, fear prevents citizens from trusting voice calls. Artha-Mesh protects users with continuous waveform tracking and a 1-click <strong>Auditory Verification</strong> check — letting your own ears verify authentic human tone and breath.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* SECTION 1: THE FOUR PILLARS */}
      <section className="impact-section" aria-labelledby="pillars-heading">
        <h2 id="pillars-heading">
          <Sparkles size={22} className="text-primary" />
          The Four Pillars of Technical Differentiation
        </h2>
        <p className="impact-section-desc">
          Instead of relying on black-box, uninspectable speech translation, Artha-Mesh delivers an airtight operational system designed for high-stakes Indian enterprise coordination:
        </p>

        <div className="pillars-grid">
          <div className="pillar-card">
            <div>
              <div className="pillar-num">Pillar 01</div>
              <div className="pillar-title">Dual-Language Synchronous Ribbon</div>
              <p className="pillar-desc">
                Renders translated output alongside original spoken transcript in a synchronized ribbon. Bilingual supervisors and enterprise coordinators can cross-check terminology and catch translation drift in real-time.
              </p>
            </div>
            <Badge tone="green">Delivered</Badge>
          </div>

          <div className="pillar-card">
            <div>
              <div className="pillar-num">Pillar 02</div>
              <div className="pillar-title">Visual Entity Tagging &amp; Turn Consensus</div>
              <p className="pillar-desc">
                High-risk quantities (e.g. <code>1976</code>, <code>200</code>) and critical negation directives (e.g. <code>नहीं</code>, <code>இல்லை</code>, <code>not</code>) are automatically tagged in visual highlight tokens with a 1-click inline <code>[✓ Confirm]</code> consensus button.
              </p>
            </div>
            <Badge tone="green">Delivered</Badge>
          </div>

          <div className="pillar-card">
            <div>
              <div className="pillar-num">Pillar 03</div>
              <div className="pillar-title">Cryptographic B2B Deal Memorandum</div>
              <p className="pillar-desc">
                Completed conversations generate an institutional Deal Memorandum with confirmation ratios, extracted parameters, and an immutable 64-character SHA-256 audit hash embedded directly into exported transcripts for non-repudiation.
              </p>
            </div>
            <Badge tone="green">Delivered</Badge>
          </div>

          <div className="pillar-card">
            <div>
              <div className="pillar-num">Pillar 04</div>
              <div className="pillar-title">VoiceShield: Waveform DSP Tracking + Auditory Human Check</div>
              <p className="pillar-desc">
                100% waveform DSP tracking (autocorrelation pitch period, spectral jitter/shimmer proxies, and AASIST graph neural embeddings) running on local server CPU with zero keyword filtering. When an anomaly is flagged, users can tap <code>[🎧 Hear Original Voice]</code> to verify authentic human breath, cadence, and inflection directly.
              </p>
            </div>
            <Badge tone="green">Delivered</Badge>
          </div>
        </div>
      </section>

      {/* SECTION 2: THE CORE PROBLEM */}
      <section className="impact-section" aria-labelledby="problem-heading">
        <h2 id="problem-heading">
          <FileCheck2 size={22} className="text-primary" />
          The Core Problem: Translation Drift When Details Matter
        </h2>
        <p className="impact-section-desc">
          Multilingual speech translation already exists in consumer tools. However, receiving translated audio does not establish that the intended meaning survived. Google explicitly documents that speech translation models produce semantic and factual errors (
          <a
            href="https://support.google.com/meet/answer/16221730?hl=en"
            target="_blank"
            rel="noopener noreferrer"
            className="evidence-link"
          >
            Google Meet documentation <ExternalLink size={12} />
          </a>
          ).
        </p>

        <div className="coordination-scenario-card">
          <div className="scenario-dialogue">
            <div className="dialogue-turn">
              <div className="dialogue-speaker">
                <span>Coordinator (Hindi speaker)</span>
                <Badge tone="neutral">Intended Operational Meaning</Badge>
              </div>
              <p className="dialogue-text">
                &ldquo;कल सुबह 10 बजे मुख्य गेट पर मिलते हैं, 11 बजे नहीं। नीली फाइल लानी है, लाल वाली नहीं।&rdquo;
              </p>
            </div>

            <div className="dialogue-turn error-case">
              <div className="dialogue-speaker">
                <span>Listener (Tamil speaker) — Passive Translation Subtitle</span>
                <Badge tone="orange">Vulnerability: Silent Translation Drift</Badge>
              </div>
              <p className="dialogue-text">
                &ldquo;நாளை காலை 11 மணிக்கு பிரதான வாயிலில் சந்திப்போம்...&rdquo;
              </p>
              <div className="dialogue-diff">
                <AlertTriangle size={15} />
                <span>Negation dropped; 10:00 AM inverted into 11:00 AM without any participant warning.</span>
              </div>
            </div>
          </div>
          <p className="impact-section-desc" style={{ marginBottom: 0 }}>
            <strong>Our Own Measured Evidence:</strong> During live batch testing on Gnani STT, the spoken year <strong>1976</strong> was recognized as <strong>1972</strong>. In casual chat, this is harmless; in banking, legal, or emergency instructions, an unnoticed digit inversion causes real-world failure. Artha-Mesh pairs translated speech with a <strong>Dual-Language Caption Ribbon</strong>, <strong>Visual Entity Tagging for numbers (e.g. <code>1976</code>, <code>200</code>) and negation (e.g. <code>नहीं</code>, <code>இல்லை</code>, <code>not</code>)</strong>, and an <strong>Inline 1-Click Confirmation Step</strong> for critical handovers.
          </p>
        </div>
      </section>

      {/* SECTION 3: VERIFIED CONTEXT */}
      <section className="impact-section" aria-labelledby="context-heading">
        <h2 id="context-heading">
          <Clock size={22} className="text-primary" />
          Verified Context: Why India, in Real Numbers
        </h2>
        <p className="impact-section-desc">
          Every figure is cited from official government or industry publications, accompanied by what the data supports and what it does not establish.
        </p>

        <div className="evidence-grid">
          <div className="evidence-card">
            <div className="evidence-header">
              <div className="evidence-metric">87 Crore</div>
              <div className="evidence-title">Indic-Language Internet Users (2024)</div>
            </div>
            <div className="evidence-details">
              <div className="evidence-supports">
                <strong>Supports:</strong> Indian-language voice experiences address a substantial, majority national audience.
              </div>
              <div className="evidence-limits">
                <strong>Does not establish:</strong> That all 87 crore users cannot speak English or all require conference translation.
              </div>
            </div>
            <div className="evidence-footer">
              <span>IAMAI–Kantar Report (Page 13)</span>
              <a
                href="https://www.iamai.in/sites/default/files/research/Kantar_%20IAMAI%20report_2024_.pdf"
                target="_blank"
                rel="noopener noreferrer"
                className="evidence-link"
              >
                Source <ExternalLink size={12} />
              </a>
            </div>
          </div>

          <div className="evidence-card">
            <div className="evidence-header">
              <div className="evidence-metric">57%</div>
              <div className="evidence-title">Urban Preference for Indic Content (2024)</div>
            </div>
            <div className="evidence-details">
              <div className="evidence-supports">
                <strong>Supports:</strong> Language preference is decisive even across connected Tier-1 and Tier-2 urban hubs.
              </div>
              <div className="evidence-limits">
                <strong>Does not establish:</strong> A measured failure rate for English-medium professional meetings.
              </div>
            </div>
            <div className="evidence-footer">
              <span>IAMAI–Kantar Report (Page 13)</span>
              <a
                href="https://www.iamai.in/sites/default/files/research/Kantar_%20IAMAI%20report_2024_.pdf"
                target="_blank"
                rel="noopener noreferrer"
                className="evidence-link"
              >
                Source <ExternalLink size={12} />
              </a>
            </div>
          </div>

          <div className="evidence-card">
            <div className="evidence-header">
              <div className="evidence-metric">₹22,495 Cr</div>
              <div className="evidence-title">Reported Financial Cyber Fraud (2025)</div>
            </div>
            <div className="evidence-details">
              <div className="evidence-supports">
                <strong>Supports:</strong> Telephony impersonation, fraud, and digital trust are urgent national concerns.
              </div>
              <div className="evidence-limits">
                <strong>Does not establish:</strong> The portion caused by AI voice clones, or losses Artha-Mesh directly prevents.
              </div>
            </div>
            <div className="evidence-footer">
              <span>Ministry of Home Affairs (11 Feb 2026)</span>
              <a
                href="https://www.pib.gov.in/PressReleasePage.aspx?PRID=2226441"
                target="_blank"
                rel="noopener noreferrer"
                className="evidence-link"
              >
                PIB Release <ExternalLink size={12} />
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* SECTION 4: FAIR ALTERNATIVES COMPARISON */}
      <section className="impact-section" aria-labelledby="comparison-heading">
        <h2 id="comparison-heading">
          <Layers size={22} className="text-primary" />
          Objective Competitor Comparison (Fair Evaluation)
        </h2>
        <p className="impact-section-desc">
          We do not claim that competitors cannot translate speech or detect deepfakes. Here is what vendor documentation establishes and the exact engineering differentiation of Artha-Mesh:
        </p>

        <div className="comparison-container">
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Solution</th>
                <th>What Its Documentation Establishes</th>
                <th>Engineering Differentiation in Artha-Mesh</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="solution-name">
                  Google Meet{' '}
                  <a
                    href="https://support.google.com/meet/answer/16221730?hl=en"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="evidence-link"
                  >
                    <ExternalLink size={12} />
                  </a>
                </td>
                <td>
                  Spoken translation across 63 languages (including Hindi, Tamil, Bengali, Telugu, and Marathi); translated captions and participant consent.
                </td>
                <td>
                  Five-language translation alone is not our differentiator. Our contribution is the synchronous dual-language ribbon, entity verification, and sovereign custody.
                </td>
                <td>
                  <Badge tone="neutral">Documented</Badge>
                </td>
              </tr>
              <tr>
                <td className="solution-name">
                  Wordly{' '}
                  <a
                    href="https://help.wordly.ai/about-languages-supported"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="evidence-link"
                  >
                    <ExternalLink size={12} />
                  </a>
                </td>
                <td>
                  Multilingual interpretation infrastructure; maintains differing speaker and attendee language lists.
                </td>
                <td>
                  We focus on true bidirectional multi-party conversation and verifiable meeting handovers rather than headline language counts.
                </td>
                <td>
                  <Badge tone="neutral">Documented</Badge>
                </td>
              </tr>
              <tr>
                <td className="solution-name">
                  BHASHINI{' '}
                  <a
                    href="https://dibd-bhashini.gitbook.io/bhashini-apis/available-models-for-usage"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="evidence-link"
                  >
                    <ExternalLink size={12} />
                  </a>
                </td>
                <td>
                  Indian-language speech recognition, translation, and speech synthesis APIs available for developer usage.
                </td>
                <td>
                  Combining STT + MT + TTS is an established industry pattern. Our technical contribution is the real-time conferencing mesh and telemetry engineering.
                </td>
                <td>
                  <Badge tone="neutral">Documented</Badge>
                </td>
              </tr>
              <tr>
                <td className="solution-name">
                  Truecaller AI Scanner{' '}
                  <a
                    href="https://support.truecaller.com/support/solutions/articles/81000413994-ai-call-scanner-faqs"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="evidence-link"
                  >
                    <ExternalLink size={12} />
                  </a>
                </td>
                <td>
                  User-triggered AI voice scanner during calls, placing the call on hold briefly; beta available in India.
                </td>
                <td>
                  In-call voice analysis is already being deployed commercially. In-call screening is an emerging norm rather than our invention.
                </td>
                <td>
                  <Badge tone="neutral">Documented</Badge>
                </td>
              </tr>
              <tr>
                <td className="solution-name">
                  Pindrop Pulse{' '}
                  <a
                    href="https://www.pindrop.com/pulse-for-meetings"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="evidence-link"
                  >
                    <ExternalLink size={12} />
                  </a>
                </td>
                <td>
                  Real-time deepfake detection for enterprise video meetings with audio/video liveness verification signals.
                </td>
                <td>
                  Neither real-time detection nor meeting integration is novel by itself. Our contribution is open, inspectable local CPU waveform telemetry with zero keyword inspection.
                </td>
                <td>
                  <Badge tone="neutral">Documented</Badge>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* SECTION 5: WHAT WE HAVE ACTUALLY MEASURED */}
      <section className="impact-section" aria-labelledby="metrics-heading">
        <h2 id="metrics-heading">
          <Gauge size={22} className="text-primary" />
          What We Have Actually Measured (Empirical Benchmarks)
        </h2>
        <p className="impact-section-desc">
          We report verified technical measurements from our live provider test batches without inflating them into broader marketing claims.
        </p>

        <div className="telemetry-grid">
          <div className="telemetry-card">
            <div className="telemetry-num">9 of 10</div>
            <div className="telemetry-label">
              <strong>Planned routes delivered decoded audio</strong> across Hindi, Tamil, Bengali, Telugu, and Marathi. (Bengali ➔ Marathi failed during local setup before API calls).
            </div>
          </div>

          <div className="telemetry-card">
            <div className="telemetry-num">1.56s</div>
            <div className="telemetry-label">
              <strong>Median server translation &amp; synthesis stage</strong> (1.37s – 2.32s range in the saved batch). Does not measure physical listener ear delay.
            </div>
          </div>

          <div className="telemetry-card">
            <div className="telemetry-num" style={{ color: '#f59e0b' }}>Unmeasured</div>
            <div className="telemetry-label">
              <strong>Physical listener latency</strong> remains unmeasured (under-2.00s is our engineering target, requiring a shared acoustic recording clock).
            </div>
          </div>

          <div className="telemetry-card">
            <div className="telemetry-num" style={{ color: '#10b981' }}>₹3.14 · $0.60</div>
            <div className="telemetry-label">
              <strong>Resource usage for the 10-route batch</strong> (estimated ₹3.14 on Gnani credits, ~$0.60 on Modal meter; not lifetime invoices).
            </div>
          </div>
        </div>
        <p className="impact-section-desc" style={{ marginTop: '0.75rem' }}>
          Explore complete raw timing traces, p50/p95 distributions, and failure logs on the{' '}
          <Link to="/performance" className="evidence-link">
            Live Performance Page <ArrowRight size={13} />
          </Link>
          .
        </p>
      </section>

      {/* SECTION 6: VOICESHIELD RESEARCH */}
      <section className="impact-section" aria-labelledby="voiceshield-heading">
        <h2 id="voiceshield-heading">
          <ShieldCheck size={22} className="text-primary" />
          VoiceShield Research: Waveform Tracking Telemetry
        </h2>
        <p className="impact-section-desc">
          VoiceShield is an experimental acoustic waveform screening module. It operates strictly on a <strong>voice tracking basis</strong> (waveform DSP and neural vocoder analysis)—<strong>not on text keywords or transcript regex</strong>.
        </p>

        <div className="voiceshield-research-box">
          <div className="voiceshield-pills">
            <span className="voiceshield-pill">Pure Voice Tracking</span>
            <span className="voiceshield-pill">Zero Text/Keyword Matching</span>
            <span className="voiceshield-pill">Local CPU Execution</span>
            <span className="voiceshield-pill">AASIST ONNX Model</span>
            <span className="voiceshield-pill">Non-Blocking Monitor Mode</span>
          </div>

          <p className="impact-section-desc" style={{ marginBottom: '1rem' }}>
            VoiceShield extracts consecutive 16kHz audio frames to calculate real-time autocorrelation pitch period variance, consecutive-frame jitter/shimmer proxies, and deepfake acoustic anomaly scores via an MIT-licensed AASIST ONNX model running entirely on the server CPU (zero external API calls).
          </p>

          <div className="voiceshield-stats">
            <div className="voiceshield-stat">
              <strong>4.04 Seconds</strong>
              <span>Required audio window (64,600 samples)</span>
            </div>
            <div className="voiceshield-stat warn">
              <strong>14 / 50 Flagged</strong>
              <span>Human clips marked suspicious in FLEURS pilot</span>
            </div>
            <div className="voiceshield-stat warn">
              <strong>12 / 50 Unknown</strong>
              <span>Human clips with inconclusive results</span>
            </div>
            <div className="voiceshield-stat">
              <strong>0 Synthetic Clips</strong>
              <span>Tested in human pilot (recall uncalibrated)</span>
            </div>
          </div>

          <p className="impact-section-desc" style={{ margin: '1rem 0 0', fontSize: '0.85rem', color: '#94a3b8' }}>
            <strong>Scientific Boundary:</strong> Because the pilot falsely flagged 28% of clean human speech clips and had zero synthetic samples, VoiceShield runs strictly in <strong>monitor mode</strong> (non-blocking risk telemetry). It explicitly separates original speaker audio from legitimate translated synthetic speech produced by Artha-Mesh.
          </p>
        </div>
      </section>

      {/* SECTION 7: ENGINEERING RIGOR */}
      <section className="impact-section" aria-labelledby="rigor-heading">
        <h2 id="rigor-heading">
          <Cpu size={22} className="text-primary" />
          Engineering Rigor &amp; Deliverables
        </h2>
        <p className="impact-section-desc">
          To maintain engineering integrity, we clearly distinguish between our local verified prototype and prospective sovereign production deployment:
        </p>

        <div className="rigor-box">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
            <strong style={{ color: '#fff', fontSize: '1.05rem' }}>Automated Verification Suite Status</strong>
            <Badge tone="green">100% Green Across Repo</Badge>
          </div>
          <div className="rigor-stats">
            <div className="rigor-stat">
              <strong>1,370 Passed</strong>
              <span>Backend Pytest tests (Prisma STT, Evon MT, Timbre TTS, LiveKit DAG)</span>
            </div>
            <div className="rigor-stat">
              <strong>276 Passed</strong>
              <span>Frontend Vitest tests across 37 test suites</span>
            </div>
            <div className="rigor-stat">
              <strong>1,646 Total</strong>
              <span>Automated tests passing with 0 failures</span>
            </div>
          </div>
        </div>

        <ul style={{ color: '#cbd5e1', lineHeight: '1.7', fontSize: '0.92rem', paddingLeft: '1.25rem', marginTop: '1.25rem' }}>
          <li>
            <strong>Verified Today:</strong> Docker container builds, HTTPS/TURN (Caddy) configuration, LiveKit SFU multi-party routing, and streaming clause MT+TTS running in a 100% reproducible test suite.
          </li>
          <li>
            <strong>Sovereignty Reality:</strong> Full data sovereignty and air-gapped guarantees require physical deployment on Indian bare-metal infrastructure (such as Yotta or local on-premise clusters) under operator custody.
          </li>
          <li>
            <strong>Submission Deliverable:</strong> Open-source repository, 1,646 passing automated tests, inspectable live telemetry, and a 60-second demonstration video.
          </li>
        </ul>
      </section>
    </div>
  );
}
