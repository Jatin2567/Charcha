import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  Check,
  ChevronRight,
  CircleHelp,
  Cloud,
  FileCode2,
  Gauge,
  Globe2,
  KeyRound,
  LockKeyhole,
  RefreshCw,
  Server,
  ShieldCheck,
  Users,
} from 'lucide-react';
import { Badge, PageHeading } from '../components/ui';
import { DEPLOYMENT_FIELDS, fetchDeployment } from '../services/deployment';
import type { DeploymentSnapshot } from '../services/deployment';
import './Deployment.css';

const inputs = [
  {
    icon: Server,
    title: 'An India-hosted Linux server',
    caption: 'Infrastructure access',
    detail:
      'Ubuntu 24.04 LTS, a public IPv4 address, Docker support and firewall control for WebRTC UDP. SSH access is needed to install and operate the stack.',
    note: 'A general-purpose VM is the starting point. Choose capacity after measuring your intended room size.',
  },
  {
    icon: Globe2,
    title: 'A domain you can configure',
    caption: 'Three DNS records',
    detail:
      'Point app, media and turn subdomains to the server. They provide the application, secure LiveKit signalling and a TURN fallback for restrictive networks.',
    note: 'Trusted HTTPS and correct DNS are needed for microphone permissions and public connectivity.',
  },
  {
    icon: KeyRound,
    title: 'Gnani speech credentials',
    caption: 'Your approved account',
    detail:
      'Provide access to Prisma STT, Timbre TTS and voice-clone embeddings. Confirm the enabled models, endpoint contract and your actual credit allowance.',
    note: 'Keep credentials in the server environment. This page never asks you to enter or upload a key.',
  },
  {
    icon: AudioLines,
    title: 'A working Evon endpoint',
    caption: 'Translation compute',
    detail:
      'Provide the actual inference URL, served model name and authentication details. The current adapter expects an OpenAI-compatible /v1 chat-completions API.',
    note: 'Use approved hosted access if its contract matches, or run the open model on suitable GPU infrastructure.',
  },
];

const providers = [
  {
    name: 'E2E Networks',
    label: 'VM candidate',
    detail:
      'Indian infrastructure with documented public-IP and UDP firewall controls. Confirm the selected region, VM allowance and bandwidth terms before ordering.',
    href: 'https://docs.e2enetworks.com/docs/myaccount/network/security_grp/',
    link: 'Network documentation',
  },
  {
    name: 'Zoho Catalyst',
    label: 'Student program',
    detail:
      'Eligible non-commercial student projects can receive up to $250 over six months. AppSail is managed application hosting; a public-UDP LiveKit VM is not documented.',
    href: 'https://catalyst.zoho.com/students/',
    link: 'Eligibility & allowance',
  },
  {
    name: 'Gnani',
    label: 'AI service access',
    detail:
      'The internship advertises 5,000 API credits. Evon has selected closed-beta API access; request its actual quickstart and confirm whether your allowance covers it. Free VM or GPU access is not promised.',
    href: 'https://www.gnani.ai/evon-waitlist',
    link: 'Evon access details',
  },
];

function SettingState({ value }: { value: boolean | null }) {
  return (
    <Badge tone={value === true ? 'green' : value === false ? 'orange' : 'neutral'}>
      {value === true && <Check size={11} />}
      {value === true ? 'Present' : value === false ? 'Missing' : 'Unknown'}
    </Badge>
  );
}

export function Deployment() {
  const [snapshot, setSnapshot] = useState<DeploymentSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = setTimeout(() => controller.abort(), 10000);
    setLoading(true);
    setFailed(false);
    void fetchDeployment(controller.signal)
      .then((value) => {
        if (active) setSnapshot(value);
      })
      .catch(() => {
        if (active) {
          setSnapshot(null);
          setFailed(true);
        }
      })
      .finally(() => {
        clearTimeout(timeout);
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [refresh]);

  const required = DEPLOYMENT_FIELDS.filter((field) => field.required);
  const present = required.filter((field) =>
    snapshot?.fields.some((state) => state.key === field.key && state.configured === true),
  ).length;

  return (
    <div className="deployment-page">
      <PageHeading
        eyebrow="FROM WORKSPACE TO YOUR SERVER"
        title="Deployment setup."
        description="Bring your infrastructure and approved AI access. Keep every setup requirement in one place."
        action={
          <Link className="button secondary" to="/performance">
            <Gauge size={16} />
            View performance <ArrowUpRight size={15} />
          </Link>
        }
      />

      <section className="deployment-intro">
        <span className="deployment-intro-icon">
          <Server size={25} />
        </span>
        <div>
          <div className="deployment-intro-heading">
            <h2>Your server. Your media infrastructure.</h2>
            <Badge tone="green">Self-hosted LiveKit</Badge>
          </div>
          <p>
            Run the application, API, room agent and LiveKit on an India-hosted Linux VM. LiveKit
            Cloud credits are unnecessary for this deployment. Your VM, bandwidth and AI providers
            still have their own costs.
          </p>
        </div>
      </section>

      <section className="deployment-architecture" aria-labelledby="deployment-architecture-title">
        <div className="deployment-section-heading">
          <div>
            <span className="eyebrow">THE DEPLOYMENT MAP</span>
            <h2 id="deployment-architecture-title">A clear home for each service</h2>
          </div>
          <span>Single-server starting point</span>
        </div>
        <div className="deployment-flow">
          <article className="deployment-flow-card deployment-flow-client">
            <span className="deployment-flow-icon">
              <Users size={21} />
            </span>
            <h3>Your participants</h3>
            <p>Browser microphone and speaker</p>
            <span className="deployment-flow-tag">HTTPS · WebRTC</span>
          </article>
          <span className="deployment-flow-arrow" aria-hidden="true">
            <ArrowRight size={21} />
            <ArrowDown size={21} />
          </span>
          <article className="deployment-flow-card deployment-flow-server">
            <span className="deployment-flow-icon">
              <Server size={21} />
            </span>
            <h3>Your India VM</h3>
            <p>Web app · Python API · room agent</p>
            <div className="deployment-server-services">
              <span>LiveKit</span>
              <span>TURN</span>
              <span>Usage ledger</span>
            </div>
          </article>
          <span className="deployment-flow-arrow" aria-hidden="true">
            <ArrowRight size={21} />
            <ArrowDown size={21} />
          </span>
          <div className="deployment-provider-stack">
            <article>
              <Cloud size={18} />
              <div>
                <h3>Gnani speech APIs</h3>
                <p>Recognition · speech · voice embeddings</p>
              </div>
            </article>
            <article>
              <AudioLines size={18} />
              <div>
                <h3>Evon translation</h3>
                <p>Approved hosted API or separate GPU</p>
              </div>
            </article>
          </div>
        </div>
        <div className="deployment-residency">
          <ShieldCheck size={17} />
          <p>
            For an India-only claim, verify processing, storage, logs, backups and provider access
            for every service. Selecting an Indian VM alone does not establish end-to-end data
            residency.
          </p>
        </div>
      </section>

      <section aria-labelledby="deployment-inputs-title">
        <div className="deployment-section-heading">
          <div>
            <span className="eyebrow">WHAT YOU PROVIDE</span>
            <h2 id="deployment-inputs-title">Four inputs to connect the stack</h2>
          </div>
          <span>Credentials stay on the server</span>
        </div>
        <div className="deployment-inputs">
          {inputs.map((input, index) => (
            <article className="deployment-input" key={input.title}>
              <div className="deployment-input-top">
                <span className="deployment-input-icon">
                  <input.icon size={20} />
                </span>
                <span>0{index + 1}</span>
              </div>
              <small>{input.caption}</small>
              <h3>{input.title}</h3>
              <p>{input.detail}</p>
              <div className="deployment-input-note">{input.note}</div>
            </article>
          ))}
        </div>
      </section>

      <section className="deployment-readiness" aria-labelledby="deployment-readiness-title">
        <div className="deployment-section-heading">
          <div>
            <span className="eyebrow">READ-ONLY SERVER CHECK</span>
            <h2 id="deployment-readiness-title">Configuration presence</h2>
          </div>
          <button
            className="button secondary"
            onClick={() => setRefresh((value) => value + 1)}
            disabled={loading}
          >
            <RefreshCw size={15} className={loading ? 'spin' : ''} />
            {loading ? 'Checking…' : 'Refresh status'}
          </button>
        </div>
        <div className="deployment-readiness-summary" aria-live="polite">
          <div>
            <strong>{loading ? '…' : snapshot ? `${present} / ${required.length}` : '—'}</strong>
            <span>required settings present</span>
          </div>
          <Badge tone={snapshot?.mode === 'live' ? 'green' : 'neutral'}>
            {loading
              ? 'Checking service'
              : snapshot
                ? `${snapshot.mode === 'live' ? 'Live' : 'Demo'} server`
                : 'Service unavailable'}
          </Badge>
          <p>
            Presence confirms that a value is set. It does not verify that credentials work, that a
            provider is reachable, or that the server can carry a public call.
          </p>
        </div>
        {failed && (
          <div className="deployment-offline" role="status">
            <CircleHelp size={18} />
            <span>
              The workspace service is unavailable. Settings below are shown for reference and their
              status is unknown. Connect your deployed API, then refresh.
            </span>
          </div>
        )}
        {!!snapshot?.configuration_issues.length && !loading && (
          <div className="deployment-issues" role="status">
            <CircleHelp size={18} />
            <div>
              <strong>Static configuration needs attention</strong>
              <p>
                Resolve these server settings before public deployment. Passing these checks still
                leaves DNS, TLS, firewall and provider access to verify.
              </p>
              <ul>
                {snapshot.configuration_issues.map((issue, index) => (
                  <li key={`${issue.key}-${index}`}>
                    <code>{issue.key}</code>
                    <span>{issue.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
        <div className="deployment-setting-list">
          {DEPLOYMENT_FIELDS.map((field) => (
            <div className="deployment-setting" key={field.key}>
              <div className="deployment-setting-title">
                <strong>{field.label}</strong>
                <span>{field.required ? 'Required' : 'Conditional / default'}</span>
                <code>{field.key}</code>
              </div>
              <p>{field.detail}</p>
              <SettingState
                value={
                  loading
                    ? null
                    : (snapshot?.fields.find((state) => state.key === field.key)?.configured ??
                      null)
                }
              />
            </div>
          ))}
        </div>
        <div className="deployment-readiness-foot">
          <LockKeyhole size={14} />
          <span>
            One read-only request on opening or refresh. No provider probes, microphone capture or
            API-credit use.
          </span>
          {snapshot && (
            <time dateTime={snapshot.generated_at}>
              Updated{' '}
              {new Date(snapshot.generated_at).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </time>
          )}
        </div>
      </section>

      <section className="deployment-launch" aria-labelledby="deployment-launch-title">
        <span className="deployment-launch-icon">
          <FileCode2 size={24} />
        </span>
        <div>
          <span className="eyebrow">PREPARED IN THE CODEBASE</span>
          <h2 id="deployment-launch-title">Generate, deploy, then verify with real speech</h2>
          <p>
            Use the deployment generator to prepare your domain configuration and local LiveKit
            credentials. Follow the production guide to install the stack, then test public
            connectivity from two devices before enabling paid speech.
          </p>
          <div className="deployment-source-files">
            <code>scripts/prepare_deployment.py</code>
            <ChevronRight size={14} />
            <code>deploy/production/README.md</code>
          </div>
        </div>
        <Link to="/development" className="text-link">
          Development record <ArrowUpRight size={14} />
        </Link>
      </section>

      <section aria-labelledby="deployment-hosting-title">
        <div className="deployment-section-heading">
          <div>
            <span className="eyebrow">INDIAN HOSTING & ALLOWANCES</span>
            <h2 id="deployment-hosting-title">Choose the right service for each job</h2>
          </div>
          <span>Official references · 24 Oct 2026</span>
        </div>
        <div className="deployment-hosting-grid">
          {providers.map((provider) => (
            <article className="deployment-host" key={provider.name}>
              <div>
                <h3>{provider.name}</h3>
                <Badge>{provider.label}</Badge>
              </div>
              <p>{provider.detail}</p>
              <a className="text-link" href={provider.href} target="_blank" rel="noreferrer">
                {provider.link}
                <ArrowUpRight size={14} />
              </a>
            </article>
          ))}
        </div>
        <div className="deployment-hosting-note">
          <CircleHelp size={16} />
          <p>
            Confirm eligibility and current terms with the provider. Zoho AppSail’s documented
            request lifecycle and networking need a separate compatibility review for an
            always-connected room agent. See{' '}
            <a
              href="https://docs.catalyst.zoho.com/en/serverless/help/appsail/appsail-basics/"
              target="_blank"
              rel="noreferrer"
            >
              AppSail limits
            </a>{' '}
            and{' '}
            <a
              href="https://www.gnani.ai/great-indian-ai-internship-registration-form"
              target="_blank"
              rel="noreferrer"
            >
              Gnani’s programme details
            </a>
            .
          </p>
        </div>
      </section>

      <div className="deployment-final-check">
        <Users size={21} />
        <div>
          <strong>The final input is a real conversation.</strong>
          <p>
            Arrange consenting Hindi, Tamil and Bengali speakers, two networks and headphones.
            Review accuracy and voice quality, then measure latency on the Performance page.
          </p>
        </div>
        <Link to="/usage" className="text-link">
          Review credit limits <ArrowUpRight size={14} />
        </Link>
      </div>
    </div>
  );
}
