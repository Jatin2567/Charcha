import { useEffect, useRef, useState } from 'react';
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
  Video,
  VideoOff,
} from 'lucide-react';
import { useApp } from '../state/AppContext';
import { AdmissionGate } from '../components/Admission';
import { getRoom, joinRoom, leaveRoom } from '../services/api';
import { useDevices, playTestTone } from '../hooks/useDevices';
import { Avatar, Badge, ErrorNotice, LanguageSelect, Loading, PageHeading } from '../components/ui';
import type { Room } from '../types/domain';
import { isScriptedLanguage } from '../types/domain';
import { useCameraPreview } from '../hooks/useCameraPreview';
import { LocalCameraPreview } from '../components/CameraVideo';
import { ConversationIllustration } from '../components/ConversationIllustration';
export function Prejoin() {
  const {code = ''} = useParams();
  return <AdmissionGate key={code} code={code}><DeviceSetup /></AdmissionGate>;
}
function DeviceSetup() {
  const { code = '' } = useParams();
  const app = useApp();
  const navigate = useNavigate();
  const devices = useDevices();
  const camera = useCameraPreview();
  const [room, setRoom] = useState<Room | null>(null);
  const [name, setName] = useState(app.preferences.name);
  const [language, setLanguage] = useState(app.preferences.language);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [speaker, setSpeaker] = useState('');
  const joining = useRef(false);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    if (app.healthLoading) return;
    if (!app.health) {
      setError(app.serviceError);
      return;
    }
    let cancelled = false;
    setError('');
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
    if (joining.current || busy || devices.pending || camera.pending) return;
    if (!name.trim()) {
      setError('Enter your display name before joining.');
      return;
    }
    if (!consent) {
      setError('Please consent to conversation processing before joining.');
      return;
    }
    if (room?.mode === 'demo' && !isScriptedLanguage(language)) {
      setError(
        'Choose Hindi, Tamil, Bengali or English for the scripted example. Other languages require live setup.',
      );
      return;
    }
    joining.current = true;
    setBusy(true);
    try {
      const m = await joinRoom(code, name.trim(), language, 'standard', consent, undefined,
        Boolean(room?.screening_switchable && consent));
      if (!alive.current) {
        void leaveRoom(m).catch(() => {});
        return;
      }
      app.setPreferences({ name: name.trim(), language, micEnabled: false });
      devices.stop();
      camera.stop();
      app.setMembership(m);
      navigate(`/room/${code}`);
    } catch (e) {
      if (alive.current) setError((e as Error).message);
    } finally {
      joining.current = false;
      if (alive.current) setBusy(false);
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
        description="Choose your language and check your microphone, speaker and camera before joining."
      />
      {!room && !error ? (
        <Loading label="Finding your conversation…" />
      ) : (
        <div className="prejoin-grid">
          <div className="prejoin-preview">
            <div className="preview-stage">
              {camera.stream && <LocalCameraPreview stream={camera.stream} />}
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
                <span style={{ visibility: camera.stream ? 'hidden' : 'visible' }}>
                  <Avatar name={name || 'You'} index={2} large />
                </span>
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
                  className={`round-control ${camera.stream ? '' : 'off'}`}
                  aria-pressed={!!camera.stream}
                  aria-label={
                    camera.pending
                      ? 'Starting camera preview'
                      : camera.stream
                        ? 'Turn camera preview off'
                        : 'Preview camera'
                  }
                  disabled={camera.pending || (room?.mode === 'demo' && !camera.stream)}
                  onClick={() => (camera.stream ? camera.stop() : void camera.start())}
                >
                  {camera.stream ? <Video size={19} /> : <VideoOff size={19} />}
                </button>
                <button
                  className={`round-control ${devices.enabled ? '' : 'off'}`}
                  aria-pressed={devices.enabled}
                  aria-label={
                    devices.pending
                      ? 'Starting microphone test'
                      : devices.enabled
                        ? 'Turn microphone test off'
                        : 'Test microphone'
                  }
                  disabled={devices.pending || busy}
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
              <p className="preview-caption">
                {camera.stream
                  ? 'Camera preview is private. Camera sharing starts off after joining.'
                  : 'Camera is off. You can turn it on after joining.'}
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
            <ErrorNotice message={camera.error} />
            <figure className="prejoin-illustration">
              <ConversationIllustration />
              <figcaption className="illustration-caption">
                One conversation. Many perspectives.
              </figcaption>
            </figure>
          </div>
          <section className="panel prejoin-form">
            <div className="panel-head">
              <h2>Ready when you are.</h2>
              <Badge tone={room?.mode === 'live' ? 'green' : 'orange'}>
                {room?.mode === 'transport'
                  ? 'Raw audio test'
                  : room?.mode === 'live'
                    ? 'Live room'
                    : 'Scripted demo'}
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
            <LanguageSelect
              label="Your speaking and listening language"
              value={language}
              onChange={setLanguage}
              scriptedOnly={room?.mode === 'demo'}
            />
            <div className="prejoin-language-note">
              <Languages size={17} />
              <p>
                {room?.mode === 'transport'
                  ? 'Local transport test: hear everyone’s original speech. Changing language does not translate audio.'
                  : 'Speak in your selected language. You’ll hear other participants translated into it.'}
              </p>
            </div>
            {room?.mode === 'live' && (
              <p className="source-note">
                Ten language choices are available. Translation quality still needs human review.
                Joining keeps your microphone and camera off; paid interpretation starts only with
                an approved flow and an explicit unmute.
              </p>
            )}
            <label className="field">
              <span>Microphone</span>
              <select
                value={app.preferences.inputDevice}
                disabled={busy || devices.pending}
                onChange={(event) => {
                  devices.stop();
                  app.setPreferences({ inputDevice: event.target.value });
                }}
              >
                <option value="default">System default microphone</option>
                {devices.inputs
                  .filter((device) => device.deviceId && device.deviceId !== 'default')
                  .map((device, index) => (
                    <option key={device.deviceId} value={device.deviceId}>
                      {device.label || `Microphone ${index + 1}`}
                    </option>
                  ))}
              </select>
            </label>
            <label className="field">
              <span>Speaker</span>
              <select
                value={app.preferences.outputDevice}
                disabled={busy}
                onChange={(event) => app.setPreferences({ outputDevice: event.target.value })}
              >
                <option value="default">System default speaker</option>
                {devices.outputs
                  .filter((device) => device.deviceId && device.deviceId !== 'default')
                  .map((device, index) => (
                    <option key={device.deviceId} value={device.deviceId}>
                      {device.label || `Speaker ${index + 1}`}
                    </option>
                  ))}
              </select>
              <small>Use system settings if output switching is unavailable.</small>
            </label>
            <div className="divider" />
            <div className="standard-voice">
              <span className="feature-icon green">
                <AudioLines size={18} />
              </span>
              <div>
                <strong>
                  {room?.mode === 'transport'
                    ? 'Original microphone audio'
                    : room?.voice_required ? 'Your voice, in their language' : 'Standard translation voice'}
                </strong>
                <small>
                  {room?.mode === 'transport'
                    ? 'Everyone hears the original language.'
                    : room?.voice_required ? 'After joining, consent and record your own 5–30 second voice reference before speaking.' : 'Participants listening in another language hear a synthesized voice.'}
                </small>
              </div>
              <Check size={16} />
            </div>
            <p className="source-note">
              {room?.mode === 'transport'
                ? 'Use headphones if another participant is in the same room.'
                : 'Choose the language you will speak and want to hear.'}
            </p>
            {room?.screening_switchable ? (
              <p className="source-note">
                VoiceShield is currently {room.screening_mode === 'monitor' ? 'on' : 'off'}. The host can switch it during the call.
                By joining, you agree that while it is on the meeting server can screen your unmuted microphone for synthetic speech
                and show the assessment to everyone in this room. You can mute or leave at any time.
              </p>
            ) : room?.screening_mode && room.screening_mode !== 'off' && (
              <p className="source-note">
                VoiceShield analyzes your microphone audio on the meeting server. Participants can see your experimental screening results.
                {room.screening_mode === 'enforce' && ' Audio is held until a window passes screening.'}
              </p>
            )}
            <label className="check-line">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              <span>
                I agree to processing my speech, text and any camera video I choose to share for
                this conversation. I can leave at any time.
              </span>
            </label>
            <ErrorNotice message={error} />
            <button
              className="button primary full"
              style={{ marginTop: 20 }}
              onClick={() => void join()}
              disabled={
                busy || devices.pending || camera.pending || !room || !name.trim() || !consent
              }
              aria-busy={busy}
            >
              {busy ? 'Joining your conversation…' : 'Join conversation'}
              <ArrowRight size={17} />
            </button>
            {!room && error && (
              <button
                className="button secondary full"
                onClick={() => {
                  setError('');
                  void app.refreshHealth();
                }}
              >
                Retry invitation
              </button>
            )}
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
