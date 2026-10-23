import { useState } from 'react';
import { Headphones, Mic, RefreshCw, Check, Server, ArrowUpRight, ShieldCheck } from 'lucide-react';
import { useApp } from '../state/AppContext';
import { useDevices, playTestTone } from '../hooks/useDevices';
import { Badge, ErrorNotice, LanguageSelect, PageHeading, Toggle, Toast } from '../components/ui';
export function Settings() {
  const { preferences, setPreferences, health, serviceError, refreshHealth, healthLoading } =
    useApp();
  const devices = useDevices();
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');
  const [name, setName] = useState(preferences.name);
  return (
    <>
      <PageHeading
        eyebrow="MAKE YOURSELF AT HOME"
        title="Your workspace, your way."
        description="A few thoughtful settings for a conversation that feels natural."
      />
      <div className="settings-grid">
        <div className="settings-stack">
          <section className="panel">
            <div className="panel-head">
              <h2>Profile & language</h2>
              <Badge tone="green">Saved on this device</Badge>
            </div>
            <p className="panel-intro">
              These preferences help you get into your next conversation.
            </p>
            <label className="field">
              <span>Your display name</span>
              <input
                value={name}
                maxLength={60}
                onChange={(e) => setName(e.target.value)}
                placeholder="How should we call you?"
              />
            </label>
            <LanguageSelect
              value={preferences.language}
              onChange={(language) => setPreferences({ language })}
            />
            <button
              className="button primary"
              onClick={() => {
                setPreferences({ name: name.trim() });
                setToast('Your profile preferences are saved.');
              }}
            >
              <Check size={15} />
              Save profile
            </button>
            <div className="divider" />
            <Toggle
              checked={preferences.autoCaptions}
              onChange={(autoCaptions) => setPreferences({ autoCaptions })}
              label="Show captions when joining"
              description="Read interpreted turns alongside your conversation."
            />
            <Toggle
              checked={preferences.highContrast}
              onChange={(highContrast) => setPreferences({ highContrast })}
              label="Stronger text contrast"
              description="Use darker supporting text in your workspace."
            />
          </section>
          <section className="panel">
            <div className="panel-head">
              <h2>Microphone & speaker</h2>
              <Headphones size={18} color="#849676" />
            </div>
            <p className="panel-intro">
              Device access is requested only when you test your microphone.
            </p>
            <label className="field">
              <span>Microphone</span>
              <select
                value={preferences.inputDevice}
                onChange={(e) => setPreferences({ inputDevice: e.target.value })}
              >
                <option value="default">System default microphone</option>
                {devices.inputs
                  .filter((d) => d.deviceId !== 'default')
                  .map((d, i) => (
                    <option key={d.deviceId} value={d.deviceId}>
                      {d.label || `Microphone ${i + 1}`}
                    </option>
                  ))}
              </select>
            </label>
            <label className="field">
              <span>Speaker</span>
              <select
                value={preferences.outputDevice}
                onChange={(e) => setPreferences({ outputDevice: e.target.value })}
              >
                <option value="default">System default speaker</option>
                {devices.outputs
                  .filter((d) => d.deviceId !== 'default')
                  .map((d, i) => (
                    <option key={d.deviceId} value={d.deviceId}>
                      {d.label || `Speaker ${i + 1}`}
                    </option>
                  ))}
              </select>
              <small>
                Output switching depends on your browser. Use system settings if unavailable.
              </small>
            </label>
            <div className="device-test-row">
              <button
                className="button secondary"
                onClick={() =>
                  devices.enabled ? devices.stop() : void devices.start(preferences.inputDevice)
                }
              >
                <Mic size={15} />
                {devices.enabled ? 'Stop microphone test' : 'Test microphone'}
              </button>
              <button
                className="button secondary"
                onClick={() =>
                  void playTestTone(preferences.outputDevice)
                    .then(() => setToast('Test tone played. Check your speaker volume.'))
                    .catch((e) => setError((e as Error).message))
                }
              >
                <Headphones size={15} />
                Play test tone
              </button>
            </div>
            {devices.enabled && (
              <div className="mic-test-meter">
                <span>Input level</span>
                <div>
                  {Array.from({ length: 24 }, (_, i) => (
                    <i key={i} className={i / 24 < devices.level ? 'lit' : ''} />
                  ))}
                </div>
              </div>
            )}
            <ErrorNotice message={devices.error || error} />
          </section>
        </div>
        <div className="settings-stack">
          <section className="panel">
            <div className="panel-head">
              <h2>Workspace connection</h2>
              <Server size={18} color="#849676" />
            </div>
            <Badge tone={health?.mode === 'live' ? 'green' : 'orange'}>
              {health?.mode === 'live'
                ? 'Live services available'
                : health
                  ? 'Scripted demonstration'
                  : 'Service unavailable'}
            </Badge>
            <p className="panel-intro">
              {health?.mode === 'live'
                ? 'The server reports live provider configuration. Join a room to test audio and interpretation.'
                : 'Demo conversations use a fixed script. Connect the backend and provider keys for live interpretation.'}
            </p>
            <ErrorNotice message={serviceError} />
            <div className="divider" />
            {health?.providers.length ? (
              <div className="provider-list">
                {health.providers.map((p) => (
                  <div className="provider-row" key={p.name}>
                    <div>
                      <strong>{p.name}</strong>
                      <Badge
                        tone={
                          p.status === 'ready' || p.status === 'configured' ? 'green' : 'orange'
                        }
                      >
                        {p.status}
                      </Badge>
                    </div>
                    <p>{p.detail}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="provider-list">
                {[
                  'LiveKit · room audio',
                  'Prisma · speech recognition',
                  'Evon · translation endpoint',
                  'Timbre · speech synthesis',
                ].map((p) => (
                  <div className="provider-row" key={p}>
                    <div>
                      <strong>{p}</strong>
                      <Badge tone="neutral">Server setup</Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <p className="source-note">
              API credentials belong in the server environment. They are never entered or stored in
              this browser.
            </p>
            <button
              className="button secondary full"
              style={{ marginTop: 18 }}
              disabled={healthLoading}
              onClick={() => void refreshHealth()}
            >
              <RefreshCw size={15} className={healthLoading ? 'spin' : ''} />
              {healthLoading ? 'Checking connection…' : 'Check connection again'}
            </button>
          </section>
          <section className="panel">
            <span className="feature-icon green">
              <ShieldCheck size={20} />
            </span>
            <h3 style={{ marginTop: 15 }}>A note on your conversation</h3>
            <p className="panel-intro">
              Room credentials stay in this tab’s session storage. Recaps are saved on this device
              only when you choose to save them. Voice references require explicit consent and can
              be deleted.
            </p>
            <a
              className="text-link"
              style={{ marginTop: 17 }}
              href="https://docs.gnani.ai/"
              target="_blank"
              rel="noreferrer"
            >
              Explore provider documentation
              <ArrowUpRight size={14} />
            </a>
          </section>
        </div>
      </div>
      {toast && <Toast message={toast} onDone={() => setToast('')} />}
    </>
  );
}
