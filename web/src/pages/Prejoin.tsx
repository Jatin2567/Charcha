import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Mic,
  MicOff,
  Headphones,
  ArrowRight,
  ArrowLeft,
  AudioLines,
  Languages,
  ShieldCheck,
  Users,
  Check,
  Volume2,
} from 'lucide-react';
import { useApp } from '../state/AppContext';
import { getRoom, joinRoom } from '../services/api';
import { useDevices, playTestTone } from '../hooks/useDevices';
import { Avatar, Badge, ErrorNotice, LanguageSelect, Loading, PageHeading } from '../components/ui';
import type { Room } from '../types/domain';
export function Prejoin() {
  const { code = '' } = useParams();
  const app = useApp();
  const navigate = useNavigate();
  const devices = useDevices();
  const [room, setRoom] = useState<Room | null>(null);
  const [name, setName] = useState(app.preferences.name);
  const [language, setLanguage] = useState(app.preferences.language);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [speaker, setSpeaker] = useState('');
  useEffect(() => {
    if (app.healthLoading) return;
    if (!app.health) {
      setError(app.serviceError);
      return;
    }
    let cancelled = false;
    void getRoom(code)
      .then((r) => {
        if (!cancelled) setRoom(r);
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [code, app.healthLoading, app.health, app.serviceError]);
  const [consent, setConsent] = useState(false);
  const join = async () => {
    if (!name.trim()) {
      setError('Enter your display name before joining.');
      return;
    }
    if (!consent) {
      setError('Please consent to conversation processing before joining.');
      return;
    }
    setBusy(true);
    try {
      const m = await joinRoom(code, name.trim(), language, 'standard', consent);
      app.setPreferences({ name: name.trim(), language, micEnabled: devices.enabled });
      devices.stop();
      app.setMembership(m);
      navigate(`/room/${code}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Link className="text-link" to="/" style={{ marginBottom: 21 }}>
        <ArrowLeft size={14} />
        Back to workspace
      </Link>
      <PageHeading
        eyebrow="A GOOD CONVERSATION STARTS HERE"
        title="Make yourself heard."
        description="Choose your language and check your audio before you come in."
      />
      {!room && !error ? (
        <Loading label="Finding your conversation…" />
      ) : (
        <div className="prejoin-grid">
          <div className="prejoin-preview">
            <div className="preview-stage">
              <div className="preview-top">
                <Badge tone="dark">
                  <AudioLines size={12} />
                  AUDIO-FIRST CONVERSATION
                </Badge>
                {room && <span className="preview-room-code">{room.code}</span>}
              </div>
              <div
                className={`preview-avatar ${devices.enabled && devices.level > 0.06 ? 'preview-speaking' : ''}`}
              >
                <Avatar name={name || 'You'} index={2} large />
              </div>
              <div className="preview-name">
                {name || 'Your name'}
                <span>You</span>
              </div>
              <div className="preview-sound">
                <span className={devices.enabled ? 'sound-on' : ''}>
                  {devices.enabled ? <Mic size={15} /> : <MicOff size={15} />}
                </span>
                <div className="waveform-static">
                  {[
                    8, 14, 23, 13, 30, 17, 26, 11, 20, 31, 13, 24, 17, 8, 22, 13, 25, 17, 30, 15, 8,
                  ].map((h, i) => (
                    <i
                      key={i}
                      style={{ height: devices.enabled ? Math.max(3, h * devices.level * 3) : 3 }}
                    />
                  ))}
                </div>
              </div>
              <div className="preview-bottom">
                <button
                  className={`round-control ${devices.enabled ? '' : 'off'}`}
                  aria-label={devices.enabled ? 'Turn microphone test off' : 'Test microphone'}
                  onClick={() =>
                    devices.enabled
                      ? devices.stop()
                      : void devices.start(app.preferences.inputDevice)
                  }
                >
                  {devices.enabled ? <Mic size={19} /> : <MicOff size={19} />}
                </button>
                <button
                  className="round-control"
                  aria-label="Test speaker"
                  onClick={() =>
                    void playTestTone(app.preferences.outputDevice)
                      .then(() => setSpeaker('Test tone played.'))
                      .catch((e) => setError((e as Error).message))
                  }
                >
                  <Volume2 size={19} />
                </button>
              </div>
              <p className="preview-caption">
                {devices.enabled
                  ? 'Microphone is on. Speak to check your level.'
                  : 'Your microphone is off. You’re in control.'}
              </p>
            </div>
            <div className="prejoin-device">
              <div>
                <Headphones size={18} />
                <span>Headphones make for a clearer conversation.</span>
              </div>
              <span>{speaker}</span>
            </div>
            <ErrorNotice message={devices.error} />
          </div>
          <section className="panel prejoin-form">
            <div className="panel-head">
              <h2>Ready when you are.</h2>
              <Badge tone={room?.mode === 'live' ? 'green' : 'orange'}>
                {room?.mode === 'live' ? 'Live room' : 'Scripted demo'}
              </Badge>
            </div>
            <p className="panel-intro">{room?.title || 'Join a conversation'}</p>
            <label className="field">
              <span>Your name</span>
              <input
                autoFocus
                maxLength={60}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Aditi Sharma"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && room) void join();
                }}
              />
            </label>
            <LanguageSelect value={language} onChange={setLanguage} />
            <div className="prejoin-language-note">
              <Languages size={17} />
              <p>
                Speak in your selected language. You’ll hear other participants translated into it.
              </p>
            </div>
            <div className="divider" />
            <div className="standard-voice">
              <span className="feature-icon green">
                <AudioLines size={18} />
              </span>
              <div>
                <strong>Standard voice to start</strong>
                <small>Enroll an optional personal voice after joining.</small>
              </div>
              <Check size={16} />
            </div>
            <p className="source-note">
              Voice enrollment requires 5–30 seconds of clean speech and your explicit permission.
            </p>
            <label className="check-line">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              <span>
                I agree to processing my speech and text for this conversation. I can leave at any
                time.
              </span>
            </label>
            <ErrorNotice message={error} />
            <button
              className="button primary full"
              style={{ marginTop: 20 }}
              onClick={() => void join()}
              disabled={busy || !room || !name.trim() || !consent}
            >
              {busy ? 'Joining your conversation…' : 'Join conversation'}
              <ArrowRight size={17} />
            </button>
            <div className="join-privacy">
              <ShieldCheck size={13} />
              <span>Joining does not record or save a recap.</span>
            </div>
            {room?.mode === 'demo' && (
              <div className="notice warning" style={{ fontSize: 9, marginBottom: 0 }}>
                <Users size={16} />
                <span>
                  Demo participants and transcript turns are scripted. No live speech recognition or
                  translation is performed.
                </span>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}
