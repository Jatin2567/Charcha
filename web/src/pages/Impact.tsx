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
        <h1>CHARCHA</h1>
        <p className="impact-subtitle">
          A prototype for multilingual conversations with original and translated captions, listener confirmations, and inspectable measurements. Designed to help people review important details across languages; high-stakes use still requires validation.
        </p>
      </header>

      {/* ILLUSTRATIVE PRODUCT PREVIEW */}
      <div className="executive-preview-hud" aria-label="Illustrative multilingual conversation preview">
        <div className="hud-header">
          <span>Illustrative WebRTC Conversation · LiveKit SFU</span>
          <Badge tone="neutral">Prototype · No SIP/PSTN gateway</Badge>
        </div>
        <div className="hud-dialogue">
          <div className="hud-turn">
            <span className="hud-meta">Example Hindi source text · not a live transcript</span>
            <div className="hud-text">&ldquo;हमें 1976 यूनिट नहीं चाहिए, सिर्फ 200 यूनिट भेजो।&rdquo;</div>
          </div>
          <div className="hud-turn">
            <span className="hud-meta">Illustrative Tamil translation · not measured audio output</span>
            <div className="hud-text">&ldquo;எங்களுக்கு 1976 அலகுகள் தேவையில்லை, 200 அலகுகளை மட்டும் அனுப்பவும்.&rdquo;</div>
          </div>
        </div>
        <div className="hud-tags">
          <div className="hud-tag">
            <Clock size={15} />
            <span><strong>1.56s</strong> Historical Server Stage Median · 31 Oct 2026</span>
          </div>
          <div className="hud-tag">
            <FileCheck2 size={15} />
            <span><strong>Dual Captions</strong> + Entity Tagging (1976, 200, नहीं/not)</span>
          </div>
          <div className="hud-tag">
            <Headphones size={15} />
            <span><strong>VoiceShield</strong> Experimental Audio Monitoring</span>
          </div>
          <div className="hud-tag">
            <CheckCircle2 size={15} />
            <span><strong>SHA-256</strong> Source Record Fingerprint</span>
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
            Across India, inter-state commerce, agricultural supply chains, emergency handovers, and personal conversations often cross language boundaries.
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
              <strong>Making Audio Warnings Inspectable</strong>
              <p>
                Charcha exposes experimental audio screening results and a <strong>Hear Original Voice</strong> control for reviewing the source audio. Neither a model score nor listening for breath and tone establishes that a caller is human or authentic.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* SECTION 1: THE FOUR PILLARS */}
      <section className="impact-section" aria-labelledby="pillars-heading">
        <h2 id="pillars-heading">
          <Sparkles size={22} className="text-primary" />
          Four Prototype Features
        </h2>
        <p className="impact-section-desc">
          Charcha combines speech translation with visible review steps and experimental audio monitoring. These features support inspection; they do not guarantee correct translations or safe high-stakes decisions.
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
              <div className="pillar-title">Visual Entity Tagging &amp; Listener Understanding</div>
              <p className="pillar-desc">
                Numbers (e.g. <code>1976</code>, <code>200</code>) and selected negation terms (e.g. <code>नहीं</code>, <code>இல்லை</code>, <code>not</code>) are highlighted for review. Listener confirmations record understanding, not agreement or proof that a translation is accurate.
              </p>
            </div>
            <Badge tone="green">Delivered</Badge>
          </div>

          <div className="pillar-card">
            <div>
              <div className="pillar-num">Pillar 03</div>
              <div className="pillar-title">Bilingual Recap &amp; Content Fingerprint</div>
              <p className="pillar-desc">
                Conversation recaps preserve original text, available translations, corrections, and listener confirmations. A SHA-256 fingerprint identifies the source record; it is not a digital signature, immutable record, or proof of agreement.
              </p>
            </div>
            <Badge tone="green">Delivered</Badge>
          </div>

          <div className="pillar-card">
            <div>
              <div className="pillar-num">Pillar 04</div>
              <div className="pillar-title">VoiceShield: Experimental Audio Monitoring</div>
              <p className="pillar-desc">
                An AASIST ONNX audio classifier runs on the server CPU. Pitch and jitter/shimmer proxies are separate diagnostics, not authenticity evidence or classifier inputs. <code>[🎧 Hear Original Voice]</code> supports audio review; detection accuracy remains unvalidated.
              </p>
            </div>
            <Badge tone="orange">Experimental</Badge>
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
          Multilingual speech translation already exists in consumer tools. However, receiving translated audio does not establish that the intended meaning survived. Google documents possible grammatical and translation errors in real-time speech translation (
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
            <strong>Saved Test Evidence (31 October 2026):</strong> In the Marathi source clip, the reference year <strong>1976</strong> was recognized as <strong>1972</strong> in two Gnani STT routes. This single example illustrates why quantities need review; it does not establish an overall error rate. Charcha pairs translated speech with a <strong>Dual-Language Caption Ribbon</strong>, <strong>Visual Entity Tagging for numbers (e.g. <code>1976</code>, <code>200</code>) and negation (e.g. <code>नहीं</code>, <code>இல்லை</code>, <code>not</code>)</strong>, and an <strong>Inline Understanding Confirmation</strong>. The dialogue above is illustrative.
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
                <strong>Supports:</strong> Indic-language internet content reaches a large audience; this is a motivation for exploring multilingual tools.
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
                <strong>Supports:</strong> A majority of surveyed urban internet users preferred Indic-language content.
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
                <strong>Supports:</strong> Reported financial cyber fraud is a substantial national concern; this total covers multiple kinds of cyber fraud.
              </div>
              <div className="evidence-limits">
                <strong>Does not establish:</strong> The portion caused by AI voice clones, or losses Charcha directly prevents.
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
          Vendor documentation checked on 9 November 2026 describes the capabilities below. Charcha&apos;s column describes its prototype focus, not independently measured superiority:
        </p>

        <div className="comparison-container">
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Solution</th>
                <th>What Its Documentation Establishes</th>
                <th>Engineering Differentiation in Charcha</th>
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
                  Our prototype combines original and translated captions, entity highlighting, and explicit listener confirmations. India-only processing is not established.
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
                  Our prototype focuses on bidirectional multi-party conversation with reviewable captions and listener confirmations.
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
                  Combining STT + MT + TTS is an established industry pattern. Our implementation adds LiveKit SFU conferencing and timing telemetry.
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
                  Our experimental audio classifier and diagnostic telemetry run on the server CPU without transcript keyword inspection. Detection performance has not been validated.
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
          These saved measurements come from the 31 October 2026 provider test batch. They describe that configuration, not current end-to-end performance or translation accuracy.
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
              <strong>Historical server translation &amp; synthesis median</strong> (1.37s – 2.32s range). Excludes microphone capture, speech recognition, and physical listener playback; it is not current end-to-end latency.
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
          Explore saved timing summaries, measurement boundaries, and failure details on the{' '}
          <Link to="/performance" className="evidence-link">
            Performance Page <ArrowRight size={13} />
          </Link>
          .
        </p>
      </section>

      {/* SECTION 6: VOICESHIELD RESEARCH */}
      <section className="impact-section" aria-labelledby="voiceshield-heading">
        <h2 id="voiceshield-heading">
          <ShieldCheck size={22} className="text-primary" />
          VoiceShield Research: Experimental Audio Screening
        </h2>
        <p className="impact-section-desc">
          VoiceShield is an experimental <strong>audio classifier</strong> with separate waveform diagnostics. It processes source audio without using text keywords or transcript regex; it does not identify callers or establish authenticity.
        </p>

        <div className="voiceshield-research-box">
          <div className="voiceshield-pills">
            <span className="voiceshield-pill">Experimental Audio Classifier</span>
            <span className="voiceshield-pill">Zero Text/Keyword Matching</span>
            <span className="voiceshield-pill">Local CPU Execution</span>
            <span className="voiceshield-pill">AASIST ONNX Model</span>
            <span className="voiceshield-pill">Non-Blocking Monitor Mode</span>
          </div>

          <p className="impact-section-desc" style={{ marginBottom: '1rem' }}>
            The AASIST ONNX classifier consumes 16 kHz audio windows on the server CPU without external API calls for screening. Separate diagnostics report autocorrelation pitch and consecutive-frame jitter/shimmer proxies. These proxies are not clinical cycle measurements, classifier inputs, or evidence of human or synthetic origin. The model score is uncalibrated.
          </p>

          <div className="voiceshield-stats">
            <div className="voiceshield-stat">
              <strong>4.0375 Seconds</strong>
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
              <span>Tested in human pilot (synthetic-speech recall unmeasured)</span>
            </div>
          </div>

          <p className="impact-section-desc" style={{ margin: '1rem 0 0', fontSize: '0.85rem', color: '#94a3b8' }}>
            <strong>Scientific Boundary:</strong> The human-only pilot falsely flagged 14 of 50 clips and returned 12 unknowns. It establishes neither synthetic-speech recall nor validated detection accuracy. VoiceShield defaults to <strong>non-blocking monitor mode</strong>; automatic blocking is not validated. Screening applies to original speaker audio, separate from Charcha&apos;s translated synthetic output.
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
          Local checks, historical provider tests, and deployment readiness are separate evidence categories. Automated tests do not establish live provider quality or production readiness.
        </p>

        <div className="rigor-box">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
            <strong style={{ color: '#fff', fontSize: '1.05rem' }}>Historical Test Snapshot · 3 November 2026</strong>
            <Badge tone="neutral">Reported in Developer Journal</Badge>
          </div>
          <div className="rigor-stats">
            <div className="rigor-stat">
              <strong>1,370 Passed</strong>
              <span>Backend tests reported in the dated journal entry</span>
            </div>
            <div className="rigor-stat">
              <strong>276 Passed</strong>
              <span>Frontend tests reported in the same entry</span>
            </div>
            <div className="rigor-stat">
              <strong>1,646 Total</strong>
              <span>Historical total; not a current checkout test result</span>
            </div>
          </div>
        </div>

        <ul style={{ color: '#cbd5e1', lineHeight: '1.7', fontSize: '0.92rem', paddingLeft: '1.25rem', marginTop: '1.25rem' }}>
          <li>
            <strong>Recorded Evidence:</strong> The journal records local container and HTTPS checks, LiveKit SFU routing fixtures, and offline streaming MT/TTS regressions. A configured deployment is not proof of live network readiness or provider performance.
          </li>
          <li>
            <strong>Deployment Boundary:</strong> India-only processing and data custody require verified hosting, provider regions, logs, and operational controls. The external-provider pipeline is not air-gapped; no sovereignty guarantee is established here.
          </li>
          <li>
            <strong>Submission Material:</strong> Repository source, dated test evidence, and inspectable telemetry are available for review. A demonstration video and final live acceptance remain submission preparation tasks.
          </li>
        </ul>
      </section>
    </div>
  );
}
