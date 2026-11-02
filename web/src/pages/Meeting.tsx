import { useCallback, useEffect, useState } from 'react';
import { CallWaveforms } from '../components/CallWaveforms';
import { useNavigate, useParams, Link } from 'react-router-dom';
import {
  ArrowRight,
  AudioLines,
  Check,
  ChevronDown,
  Copy,
  Headphones,
  Info,
  Languages,
  Link2,
  MessageSquareText,
  Mic,
  MicOff,
  PhoneOff,
  Play,
  RotateCcw,
  Settings2,
  ShieldCheck,
  ShieldQuestion,
  ShieldAlert,
  Users,
  Volume2,
  VolumeX,
  X,
  Captions,
  Download,
  LoaderCircle,
  Gauge,
  Video,
  VideoOff,
} from 'lucide-react';
import { useApp } from '../state/AppContext';
import { useRoomEvents } from '../hooks/useRoomEvents';
import { useMeetingAudio } from '../hooks/useMeetingAudio';
import { confirmTurn, leaveRoom, submitText, updateParticipant } from '../services/api';
import { demoEvent, demoLookup } from '../services/demo';
import {
  Avatar,
  Badge,
  downloadText,
  EmptyState,
  LanguageSelect,
  Logo,
  Modal,
  Toast,
} from '../components/ui';
import { ParticipantCard } from '../components/ParticipantCard';
import { TranscriptPanel } from '../components/TranscriptPanel';
import { MeetingCaptions } from '../components/MeetingCaptions';
import { ConferenceStatus } from '../components/ConferenceStatus';
import { InvitationHelp } from '../components/InvitationHelp';
import { VoiceShieldPanel } from '../components/VoiceShieldPanel';
import { activeScreeningSamples, hasVoiceFlag } from '../services/voiceShield';
import { invitationScope } from '../services/invitation';
import { useDevices } from '../hooks/useDevices';
import { openPerformancePage } from '../services/transportMetrics';
import type { Language, Membership, Recap, Turn } from '../types/domain';
import { LANGUAGES, languageName } from '../types/domain';
type SidePanel = 'transcript' | 'participants' | 'settings' | 'info' | 'shield' | null;
export function Meeting() {
  const { code } = useParams();
  const { membership } = useApp();
  if (!membership || membership.room.code !== code)
    return (
      <div className="meeting-missing">
        <Logo />
        <EmptyState
          icon={<Link2 size={28} />}
          title="Your seat is waiting."
          action={
            <Link className="button primary" to={`/join/${code}`}>
              Join this conversation
              <ArrowRight size={16} />
            </Link>
          }
        >
          Join with your name and listening language to access this room.
        </EmptyState>
      </div>
    );
  return <MeetingRoom membership={membership} />;
}
function MeetingRoom({ membership: m }: { membership: Membership }) {
  const app = useApp();
  const navigate = useNavigate();
  const { state, dispatch, connection, running, startDemo, reconnect } = useRoomEvents(m);
  const audio = useMeetingAudio(m);
  const devices = useDevices();
  const [panel, setPanel] = useState<SidePanel>(m.room.mode === 'demo' ? 'transcript' : null);
  const [captions, setCaptions] = useState(app.preferences.autoCaptions);
  const resizeCaptions = useCallback(
    () => app.setPreferences({ largeCaptions: !app.preferences.largeCaptions }),
    [app.setPreferences, app.preferences.largeCaptions],
  );
  const [leave, setLeave] = useState(false);
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [copied, setCopied] = useState(false);
  const [changingLanguage, setChangingLanguage] = useState(false);
  const isDemo = m.room.mode === 'demo';
  const isTransport = m.room.mode === 'transport';
  const room = state.room || m.room;
  const participants = room.participants.filter((p) => !p.is_agent);
  const shieldParticipants = participants.map((person) => person.id === m.participant.id ? { ...person, muted: audio.muted } : person);
  const liveScreening = activeScreeningSamples(state.screening, shieldParticipants, state.screeningStatus, !isDemo && connection === 'Connected');
  const shieldFlags = liveScreening.filter(({ sample }) => hasVoiceFlag(sample));
  const language = m.participant.language;
  const invitation = `${window.location.origin}${window.location.pathname}#/join/${room.code}`;
  const inviteScope = invitationScope(invitation);
  useEffect(() => {
    const start = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.tagName === 'SELECT' ||
        target.isContentEditable ||
        document.querySelector('dialog[open]') ||
        e.ctrlKey ||
        e.metaKey ||
        e.altKey
      )
        return;
      if (!isDemo && e.key.toLowerCase() === 'm') {
        e.preventDefault();
        void audio.toggleMic();
      }
      if (!isTransport && !e.repeat && e.key.toLowerCase() === 'c') setCaptions((c) => !c);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [audio.toggleMic, isDemo, isTransport]);
  const copyInvite = async (reviewed = false) => {
    if (!reviewed && inviteScope.kind !== 'device-link' && !isDemo) {
      setPanel('info');
      setToast('Review where this invitation works before copying it.');
      return;
    }
    try {
      await navigator.clipboard.writeText(invitation);
      setCopied(true);
      setToast(
        isDemo && m.localDemo
          ? 'Demo invitation copied. Each browser has an independent scripted demo.'
          : inviteScope.kind === 'same-computer'
            ? 'Same-computer invitation copied. Use another browser profile on this laptop.'
            : 'Invitation link copied; device connectivity still needs checking.',
      );
      setTimeout(() => setCopied(false), 3000);
    } catch {
      setPanel('info');
      setToast('Select and copy the invitation link from Room details.');
    }
  };
  const confirm = async (id: string) => {
    try {
      const confirmed = m.localDemo
        ? [
            ...new Set([
              ...(state.turns.find((t) => t.id === id)?.confirmed_by || []),
              m.participant.id,
            ]),
          ]
        : (await confirmTurn(m, id)).confirmed_by;
      dispatch(demoEvent('confirmation.updated', { utterance_id: id, confirmed_by: confirmed }));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const submit = async (text: string) => {
    setSubmitting(true);
    try {
      if (m.localDemo) {
        const translations: Partial<Record<Language, string>> = {};
        for (const l of LANGUAGES) {
          const translated = demoLookup(text, l.code);
          if (translated) translations[l.code] = translated;
        }
        if (!Object.keys(translations).length)
          throw new Error(
            'This local demo only translates sentences from the scripted example. Start the script, then copy an original or translated sentence.',
          );
        const turn: Turn = {
          id: crypto.randomUUID(),
          speaker_id: m.participant.id,
          speaker_name: m.participant.name,
          source_language: language,
          text,
          created_at: new Date().toISOString(),
          translations,
          confirmed_by: [],
          status: 'complete',
        };
        dispatch(demoEvent('transcript.final', { turn }));
      } else await submitText(m, text);
    } catch (e) {
      setError((e as Error).message);
      throw e;
    } finally {
      setSubmitting(false);
    }
  };
  const finish = async () => {
    setLeaving(true);
    let cleanupWarning = '';
    try {
      await audio.disconnect();
    } catch {
      // Local tracks are stopped before the RTC disconnect await.
      cleanupWarning = 'Audio was stopped. The media connection could not confirm disconnection.';
    }
    try {
      await leaveRoom(m);
    } catch {
      cleanupWarning =
        'You left this device. Server cleanup could not be confirmed; the membership and voice profile will expire automatically.';
    }
    const recap: Recap = {
      id: crypto.randomUUID(),
      room,
      participant: m.participant,
      turns: state.turns,
      metrics: state.metrics,
      ended_at: new Date().toISOString(),
      localDemo: !!m.localDemo,
      cleanup_warning: cleanupWarning || undefined,
    };
    app.setLatestRecap(recap);
    app.setMembership(null);
    app.setVoiceProfile(null);
    navigate(`/recap/${recap.id}`);
  };
  const changeLanguage = async (next: Language) => {
    if (changingLanguage || next === language) return;
    setChangingLanguage(true);
    try {
      await audio.disconnect();
      const updated = await updateParticipant(m, { language: next, muted: true });
      app.setMembership({
        ...m,
        participant: { ...m.participant, ...(updated as object), language: next, muted: true },
      });
      app.setPreferences({ language: next });
      dispatch(
        demoEvent('participant.updated', {
          participant: { ...m.participant, language: next, muted: true },
        }),
      );
      setToast(`Language changed to ${languageName(next)}. Microphone and camera are off.`);
    } catch (e) {
      setError((e as Error).message);
      audio.retry();
    } finally {
      setChangingLanguage(false);
    }
  };
  const rejoin = async () => {
    try {
      await audio.disconnect();
    } catch {
      /* Device capture is stopped before network cleanup. */
    }
    app.setMembership(null);
    navigate(`/join/${room.code}`);
  };
  const textBlockedReason =
    !isDemo &&
    (audio.readiness.report?.provider_flow.status !== 'approved' ||
      !audio.readiness.report.provider_flow.remaining.tts_requests ||
      !audio.readiness.report.provider_flow.remaining.mt_requests)
      ? 'Typed interpretation needs an active approved cross-language flow with available requests.'
      : '';
  const transcriptDownload = () =>
    downloadText(
      `artha-mesh-${room.code}.txt`,
      `${isDemo ? 'SCRIPTED DEMONSTRATION\n\n' : ''}${state.turns.map((t) => `${t.speaker_name}: ${t.text}\n${t.translations[language] || t.text}`).join('\n\n')}`,
    );
  const togglePanel = (next: SidePanel) => setPanel((current) => (current === next ? null : next));
  const tool = (
    label: string,
    icon: React.ReactNode,
    action: () => void,
    active = false,
    disabled = false,
    control = 'panel',
  ) => (
    <button
      className={`meeting-tool ${active ? 'tool-active' : ''}`}
      data-control={control}
      data-state={disabled ? 'unavailable' : active ? 'on' : 'off'}
      title={label}
      aria-label={label}
      aria-keyshortcuts={control === 'captions' && !disabled ? 'C' : undefined}
      aria-pressed={active}
      disabled={disabled}
      onClick={action}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
  return (
    <div className="meeting-app">
      <header className="meeting-header">
        <button
          className="meeting-logo"
          aria-label="Leave conversation and return to workspace"
          onClick={() => setLeave(true)}
        >
          <Logo />
        </button>
        <div className="meeting-title">
          <h1>
            {room.title}
            <button
              className="icon-button"
              aria-label="Room details"
              onClick={() => togglePanel('info')}
            >
              <ChevronDown size={13} />
            </button>
          </h1>
          <div>
            <span className={`meeting-status-dot ${connection === 'Connected' ? 'online' : ''}`} />
            <span>{connection === 'Connected' ? 'Room connected' : connection}</span>
            {!isDemo && connection !== 'Connected' && connection !== 'Connecting…' && (
              <button
                className="text-link"
                onClick={reconnect}
                aria-label="Reconnect captions and participant updates"
              >
                Retry updates
              </button>
            )}
            <span className="meeting-header-divider">·</span>
            <span>
              {Math.floor(elapsed / 60)
                .toString()
                .padStart(2, '0')}
              :{(elapsed % 60).toString().padStart(2, '0')}
            </span>
          </div>
        </div>
        <div className="meeting-header-actions">
          <span className="meeting-language">
            <Languages size={14} />
            {isTransport ? (
              'Original audio · no translation'
            ) : (
              <>
                Your language: <strong>{languageName(language)}</strong>
              </>
            )}
          </span>
          {!isDemo && !isTransport && <Badge tone="neutral">Standard voices</Badge>}
          <button
            className="meeting-invite"
            aria-label="Invite people"
            onClick={() => void copyInvite()}
          >
            {copied ? <Check size={14} /> : <Link2 size={14} />}
            <span>{copied ? 'Copied' : 'Invite people'}</span>
          </button>
          <Avatar name={m.participant.name} index={2} />
        </div>
      </header>
      <div className="meeting-body">
        <section className="meeting-stage">
          <div className="meeting-stage-heading">
            <div>
              <Headphones size={15} />
              <span>
                {isTransport
                  ? 'Local audio test · original voices'
                  : 'A little closer. In every language.'}
              </span>
            </div>
            <button
              className="shield-launch"
              aria-label="Open VoiceShield audio screening"
              aria-expanded={panel === 'shield'}
              aria-controls={panel === 'shield' ? 'meeting-side-panel' : undefined}
              onClick={() => togglePanel('shield')}
            >
              <ShieldQuestion size={14} />VoiceShield <small>Audio check</small>
            </button>
            <Badge tone="dark">
              <Users size={11} />
              {participants.length} in this space
            </Badge>
          </div>
          {isTransport && (
            <div className="meeting-demo-banner">
              <div>
                <AudioLines size={17} />
                <span>
                  <strong>Raw audio transport test</strong>
                  <small>
                    Hear the other participants’ original speech. Translation, captions and voice
                    cloning are disabled. No speech API is used.
                  </small>
                </span>
              </div>
              <a className="text-link" href="#/tests" target="_blank" rel="noreferrer">
                Test scripts ↗
              </a>
            </div>
          )}
          {isDemo && (
            <div className="meeting-demo-banner">
              <div>
                <span className="demo-icon">
                  <AudioLines size={17} />
                </span>
                <span>
                  <strong>Scripted demonstration</strong>
                  <small>
                    {m.localDemo
                      ? 'Runs in this browser. No audio is sent and no AI inference is performed.'
                      : 'Sample participants and canned turns. No live speech inference in demo mode.'}
                  </small>
                </span>
              </div>
              <button
                onClick={() => void startDemo().catch((e) => setError((e as Error).message))}
                disabled={running}
              >
                {running ? (
                  <LoaderCircle size={14} className="spin" />
                ) : state.demoComplete ? (
                  <RotateCcw size={14} />
                ) : (
                  <Play size={13} />
                )}
                <span>
                  {running
                    ? 'Playing example…'
                    : state.demoComplete
                      ? 'Replay example'
                      : 'Start example'}
                </span>
              </button>
            </div>
          )}
          {!isDemo && (
            <ConferenceStatus
              report={audio.readiness.report}
              error={audio.readiness.error}
              stale={audio.readiness.stale}
              mediaReady={audio.mediaReady}
              muted={audio.muted}
              playback={audio.playback}
              unlocking={audio.unlocking}
              onUnlock={() => void audio.unlock()}
              onRetry={audio.retry}
              onRejoin={() => void rejoin()}
            />
          )}
          {(error || audio.error || audio.camera.error || state.error) && (
            <div className="meeting-error" role="alert">
              <span>{error || audio.error || audio.camera.error || state.error}</span>
              <button
                className="icon-button"
                aria-label="Dismiss conversation error"
                onClick={() => {
                  setError('');
                  audio.clearError();
                  dispatch(demoEvent('error.dismiss', {}));
                }}
              >
                <X size={14} />
              </button>
            </div>
          )}
          {shieldFlags.length > 0 && (
            <div className="shield-call-alert" role="status" aria-live="polite">
              <ShieldAlert size={20} />
              <div><strong>Possible synthetic voice</strong><p>{shieldFlags.map(({ person }) => person.name).join(', ')} · Acoustic model flag. Review required.</p></div>
              <button className="button secondary" onClick={() => setPanel('shield')}>View signals</button>
            </div>
          )}
          <div className={`participant-grid grid-${Math.min(participants.length, 4)}`}>
            {participants.map((p, i) => (
              <ParticipantCard
                key={p.id}
                participant={p}
                index={i}
                self={p.id === m.participant.id}
                muted={p.id === m.participant.id ? audio.muted : p.muted}
                level={audio.levels[p.id] ?? 0}
                hand={false}
                stage={state.stages[p.id]}
                originalAudio={
                  isTransport || (p.id !== m.participant.id && p.language === language)
                }
                videoTrack={audio.videoTracks[p.id]}
                screening={liveScreening.find(({ person }) => person.id === p.id)?.sample}
              />
            ))}
          </div>
          {participants.length === 1 && (
            <div className="waiting-note">
              <Link2 size={17} />
              <div>
                <strong>There’s room for another perspective.</strong>
                <p>
                  {isTransport
                    ? 'Join the invitation in a separate browser profile or device to check original audio.'
                    : 'Invite a participant who speaks a different language to begin.'}
                </p>
              </div>
              <button onClick={() => void copyInvite()}>
                Copy invitation
                <Copy size={13} />
              </button>
            </div>
          )}
          <div className="meeting-stage-foot">
            <span role="status" aria-live="polite">
              <ShieldCheck size={13} />
              {audio.status}
            </span>
            <span>
              <AudioLines size={13} />
              Audio first. Human always.
            </span>
          </div>
        </section>
        {panel && (
          <aside className="meeting-side-panel" id="meeting-side-panel">
            <div className="meeting-panel-heading">
              <h2>
                {panel === 'shield'
                  ? 'VoiceShield'
                  : panel === 'transcript'
                  ? 'Conversation'
                  : panel === 'participants'
                    ? 'People in this space'
                    : panel === 'settings'
                      ? 'Conversation settings'
                      : 'Room details'}
              </h2>
              <div>
                {panel === 'transcript' && (
                  <button
                    className="icon-button"
                    aria-label="Download current transcript"
                    title="Download transcript"
                    onClick={transcriptDownload}
                    disabled={!state.turns.length}
                  >
                    <Download size={16} />
                  </button>
                )}
                <button
                  className="icon-button"
                  aria-label="Close side panel"
                  onClick={() => setPanel(null)}
                >
                  <X size={17} />
                </button>
              </div>
            </div>
            {panel === 'shield' ? (
              <VoiceShieldPanel
                samples={state.screening}
                participants={shieldParticipants}
                connected={isDemo || connection === 'Connected'}
                status={state.screeningStatus}
                demo={isDemo}
              />
            ) : panel === 'transcript' && isTransport ? (
              <div className="side-panel-content">
                <h3>Listen to original speech</h3>
                <p className="panel-intro">
                  This stage checks the microphone, speaker, mute and media connection. It does not
                  run speech recognition, translation or synthesis.
                </p>
                <a
                  className="button secondary full"
                  style={{ marginTop: 20 }}
                  href="#/tests"
                  target="_blank"
                  rel="noreferrer"
                >
                  Open Test lab ↗
                </a>
              </div>
            ) : panel === 'transcript' ? (
              <TranscriptPanel
                turns={state.turns}
                language={language}
                selfId={m.participant.id}
                onConfirm={confirm}
                onSubmit={submit}
                demo={isDemo}
                submitting={submitting}
                blockedReason={textBlockedReason}
              />
            ) : panel === 'participants' ? (
              <div className="side-panel-content">
                <div className="people-count">
                  {participants.length} participants{' '}
                  {isDemo && <Badge tone="orange">Includes scripted examples</Badge>}
                </div>
                {participants.map((p, i) => (
                  <div className="people-row" key={p.id}>
                    <Avatar name={p.name} index={i} />
                    <div>
                      <strong>
                        {p.name}
                        {p.id === m.participant.id ? ' (You)' : ''}
                      </strong>
                      <small>
                        {languageName(p.language)} ·{' '}
                        {p.is_demo
                          ? 'Sample participant'
                          : p.voice_mode === 'cloned'
                            ? 'Personal voice'
                            : 'Standard voice'}
                      </small>
                    </div>
                    {p.id === m.participant.id ? (
                      audio.muted ? (
                        <MicOff size={14} />
                      ) : (
                        <Mic size={14} />
                      )
                    ) : p.muted ? (
                      <MicOff size={14} />
                    ) : (
                      <AudioLines size={14} />
                    )}
                  </div>
                ))}
                <button
                  className="button primary full"
                  style={{ marginTop: 24 }}
                  onClick={() => void copyInvite()}
                >
                  <Link2 size={15} />
                  Invite a participant
                </button>
                <p className="source-note">
                  {m.localDemo
                    ? 'Browser-only demos are independent in each tab. Use the backend to connect real participants.'
                    : 'Participants need the invitation link and their own microphone permission.'}
                </p>
              </div>
            ) : panel === 'settings' ? (
              <div className="side-panel-content">
                <LanguageSelect
                  value={language}
                  scriptedOnly={isDemo}
                  onChange={(next) => void changeLanguage(next)}
                  label="I speak and want to hear"
                  id="meeting-language"
                  disabled={changingLanguage || leaving}
                />
                <p className="source-note">
                  {isTransport
                    ? 'Language selection does not change original audio in this transport test.'
                    : 'Changing language reconnects media and starts your microphone and camera off. All ten language choices need live quality review.'}
                </p>
                <label className="field">
                  <span>Microphone</span>
                  <select
                    value={app.preferences.inputDevice}
                    disabled={leaving || audio.working}
                    onChange={(event) => app.setPreferences({ inputDevice: event.target.value })}
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
                  <small>Changing the microphone reconnects media with capture off.</small>
                </label>
                <label className="field">
                  <span>Speaker</span>
                  <select
                    value={app.preferences.outputDevice}
                    disabled={leaving}
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
                  <small>Use system settings if this browser cannot switch output devices.</small>
                </label>
                <div className="divider" />
                <h3>Your voice</h3>
                <div className="meeting-voice-select">
                  <AudioLines size={19} />
                  <div>
                    <strong>
                      {isTransport
                        ? 'Original voice'
                        : m.participant.voice_mode === 'cloned'
                          ? 'Personal voice'
                          : 'Standard voice'}
                    </strong>
                    <small>
                      {isTransport
                        ? 'No synthesis or enrollment in this stage'
                        : m.participant.voice_mode === 'cloned'
                          ? 'Consent-based session profile'
                          : 'Available without enrollment'}
                    </small>
                  </div>
                </div>
                <button className="button secondary full" disabled>
                  Voice cloning · later
                </button>
                <p className="source-note">
                  This stage uses standard voices. Voice enrollment and deepfake screening are
                  outside this conference test.
                </p>
                <details>
                  <summary>Later phases</summary>
                  <p className="source-note">
                    Latency optimization and experimental deepfake detection are later work. Voice
                    cloning remains deferred. They do not block this standard-voice conference.
                  </p>
                </details>
                <div className="divider" />
                <h3>Audio playback</h3>
                <p className="source-note">{audio.status}</p>
                {m.room.mode === 'live' && <CallWaveforms session={audio.waveformSession} />}
                {m.room.mode === 'live' && (
                  <label className="audio-lab-checkbox">
                    <input
                      type="checkbox"
                      checked={audio.lowerWhileSpeaking}
                      onChange={(event) => audio.changeLowerWhileSpeaking(event.target.checked)}
                    />
                    <span>Lower incoming voices while I speak</span>
                  </label>
                )}
                <button
                  className="button secondary full"
                  style={{ marginTop: 12 }}
                  onClick={() => void audio.unlock()}
                  disabled={audio.unlocking || !audio.mediaReady}
                >
                  <Volume2 size={15} />
                  {audio.unlocking ? 'Enabling speaker…' : 'Enable speaker'}
                </button>
                {!isDemo && (
                  <button
                    className="button ghost full"
                    style={{ marginTop: 8 }}
                    onClick={audio.retry}
                  >
                    <RotateCcw size={14} />
                    Reconnect media
                  </button>
                )}
                <p className="source-note">
                  Camera starts off. Turning it on shares video with people in this room. Changing
                  language or choosing Reconnect media turns it off; use the camera button to share
                  again.
                </p>
                <div className="divider" />
                {!isDemo && (
                  <>
                    <details>
                      <summary>Advanced · receiver diagnostics</summary>
                      <h3>Receiver latency probe</h3>
                      <p className="source-note">
                        Plays a one-second test tone to you only. Measures request-to-decoded-audio
                        time, not translation latency. No provider credits.
                      </p>
                      <button
                        className="button secondary full"
                        disabled={audio.probeWorking || audio.outputMuted}
                        onClick={() => void audio.probe()}
                      >
                        <Gauge size={15} />
                        {audio.probeWorking ? 'Measuring receiver…' : 'Play receiver test tone'}
                      </button>
                      {audio.probeResult && (
                        <p className="source-note" role="status">
                          {audio.probeResult.status === 'detected'
                            ? `${audio.probeResult.elapsed_ms} ms · decoded tone detected`
                            : `${audio.probeResult.status} · no latency recorded`}
                          {' · Details on Performance.'}
                        </p>
                      )}
                    </details>
                    <div className="divider" />
                  </>
                )}
                <h3>Keyboard shortcuts</h3>
                <div className="shortcut-row">
                  <span>Toggle microphone</span>
                  <kbd>M</kbd>
                </div>
                {!isTransport && (
                  <div className="shortcut-row">
                    <span>Toggle captions</span>
                    <kbd>C</kbd>
                  </div>
                )}
              </div>
            ) : (
              <div className="side-panel-content">
                <span className="feature-icon green">
                  <AudioLines size={21} />
                </span>
                <h3 style={{ marginTop: 16 }}>{room.title}</h3>
                <p className="panel-intro">
                  {isTransport
                    ? 'A local room relaying original microphone audio.'
                    : isDemo
                      ? 'A space to explore the experience using scripted examples.'
                      : 'A video room with language-specific speech interpretation.'}
                </p>
                <div className="divider" />
                <label className="field">
                  <span>Invitation link</span>
                  <input value={invitation} readOnly onFocus={(e) => e.target.select()} />
                </label>
                {!isDemo && <InvitationHelp scope={inviteScope} />}
                <button className="button primary full" onClick={() => void copyInvite(true)}>
                  <Copy size={14} />
                  {isDemo ? 'Copy invitation' : inviteScope.copyLabel}
                </button>
                <div className="divider" />
                <h3>How this room works</h3>
                <ol className="room-howto">
                  <li>Choose the language you speak and want to hear.</li>
                  <li>
                    {isTransport
                      ? 'Your microphone reaches other participants through the local media agent.'
                      : isDemo
                        ? 'Start the fixed sample script.'
                        : 'Your microphone is routed to the interpretation agent.'}
                  </li>
                  <li>
                    {isTransport
                      ? 'Hear the original language; no interpretation is performed.'
                      : isDemo
                        ? 'Read the example in the conversation panel.'
                        : 'Hear translated speech addressed to your language.'}
                  </li>
                  <li>Confirm your understanding of important details.</li>
                  {!isDemo && !isTransport && (
                    <li>
                      When everyone uses the same language, audio is forwarded directly and
                      generated captions pause to save recognition credits.
                    </li>
                  )}
                </ol>
                <button className="button secondary full" onClick={reconnect}>
                  <RotateCcw size={14} />
                  Reconnect events
                </button>
                <button
                  className="button secondary full"
                  style={{ marginTop: 12 }}
                  onClick={() => {
                    if (!openPerformancePage())
                      setToast(
                        'Allow a new tab to open the performance page while keeping this call active.',
                      );
                  }}
                >
                  <Gauge size={14} />
                  Performance & readiness ↗
                </button>
              </div>
            )}
          </aside>
        )}
      </div>
      {captions && !isTransport && (
        <MeetingCaptions
          turns={state.turns}
          language={language}
          selfId={m.participant.id}
          demo={isDemo}
          large={app.preferences.largeCaptions}
          announce={panel !== 'transcript'}
          onResize={resizeCaptions}
          emptyMessage={
            isDemo
              ? 'Start the example to see captions for each speaker.'
              : audio.readiness.report && !audio.readiness.report.provider_flow.required
                ? 'This call is forwarding original audio. Captions appear during approved interpretation.'
                : 'Captions appear here when an approved speech turn is recognized.'
          }
        />
      )}
      <footer className="meeting-toolbar">
        <div className="meeting-toolbar-left">
          <span className="meeting-room-code">{room.code}</span>
          <button
            className={`toolbar-info ${panel === 'info' ? 'selected' : ''}`}
            aria-label="Room information"
            onClick={() => togglePanel('info')}
          >
            <Info size={17} />
          </button>
        </div>
        <div className="meeting-toolbar-center">
          {tool(
            isDemo
              ? 'Demo camera off'
              : audio.camera.pending
                ? 'Starting camera…'
                : audio.camera.enabled
                  ? 'Turn camera off'
                  : 'Turn camera on',
            audio.camera.enabled ? <Video size={20} /> : <VideoOff size={20} />,
            () => void audio.toggleCamera(),
            audio.camera.enabled,
            audio.camera.pending ||
              isDemo ||
              ((!audio.mediaReady || audio.readiness.stale) && !audio.camera.enabled) ||
              leaving,
            'camera',
          )}
          {tool(
            isDemo
              ? 'Demo mic off'
              : audio.working
                ? audio.muted
                  ? 'Starting microphone…'
                  : 'Muting…'
                : audio.muted
                  ? 'Unmute'
                  : 'Mute',
            audio.muted ? <MicOff size={20} /> : <Mic size={20} />,
            () => void audio.toggleMic(),
            !audio.muted,
            audio.working || isDemo || (audio.muted && !audio.canUnmute),
            'microphone',
          )}
          {tool(
            audio.unlocking
              ? 'Enabling speaker…'
              : audio.playback.status === 'blocked'
                ? 'Enable speaker'
                : audio.outputMuted
                  ? 'Speaker off'
                  : 'Speaker',
            audio.outputMuted ? <VolumeX size={20} /> : <Volume2 size={20} />,
            () => void audio.toggleOutput(),
            !audio.outputMuted,
            !audio.mediaReady || audio.unlocking || isDemo,
            'speaker',
          )}
          <span className="toolbar-divider" />
          {tool(
            isTransport ? 'Captions unavailable' : captions ? 'Captions on' : 'Captions off',
            <Captions size={20} />,
            () => setCaptions(!captions),
            !isTransport && captions,
            isTransport,
            'captions',
          )}
          {tool(
            'Settings',
            <Settings2 size={19} />,
            () => togglePanel('settings'),
            panel === 'settings',
          )}
          <button
            className="leave-button"
            onClick={() => setLeave(true)}
            aria-label="Leave conversation"
            disabled={leaving}
          >
            <PhoneOff size={21} />
            <span>Leave</span>
          </button>
        </div>
        <div className="meeting-toolbar-right">
          {tool(
            'People',
            <Users size={20} />,
            () => togglePanel('participants'),
            panel === 'participants',
          )}
          {tool(
            'Conversation',
            <MessageSquareText size={20} />,
            () => togglePanel('transcript'),
            panel === 'transcript',
          )}
        </div>
      </footer>
      {toast && <Toast message={toast} onDone={() => setToast('')} />}
      {leave && (
        <Modal title="Ready to step out?" onClose={() => setLeave(false)}>
          <p className="muted">
            You’ll see a recap of the conversation. You can choose to save it on this device or
            download it.
          </p>
          <div className="modal-actions">
            <button className="button secondary" disabled={leaving} onClick={() => setLeave(false)}>
              Stay a little longer
            </button>
            <button className="button danger" disabled={leaving} onClick={() => void finish()}>
              {leaving ? 'Leaving…' : 'Leave conversation'}
              <PhoneOff size={16} />
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
