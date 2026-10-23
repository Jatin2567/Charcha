import { useEffect, useState } from 'react';
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
  Users,
  Volume2,
  VolumeX,
  X,
  Captions,
  Download,
  LoaderCircle,
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
import { VoiceEnrollment } from '../components/VoiceEnrollment';
import type { Language, Membership, Recap, Turn } from '../types/domain';
import { LANGUAGES, languageName } from '../types/domain';
type SidePanel = 'transcript' | 'participants' | 'settings' | 'info' | null;
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
  const [panel, setPanel] = useState<SidePanel>('transcript');
  const [captions, setCaptions] = useState(app.preferences.autoCaptions);
  const [leave, setLeave] = useState(false);
  const [enroll, setEnroll] = useState(false);
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [copied, setCopied] = useState(false);
  const isDemo = m.room.mode === 'demo';
  const room = state.room || m.room;
  const participants = room.participants.filter((p) => !p.is_agent);
  const latest = state.turns[state.turns.length - 1];
  const language = m.participant.language;
  const invitation = `${window.location.origin}${window.location.pathname}#/join/${room.code}`;
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
      if (e.key.toLowerCase() === 'c') setCaptions((c) => !c);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [audio.toggleMic]);
  const copyInvite = async () => {
    try {
      await navigator.clipboard.writeText(invitation);
      setCopied(true);
      setToast(
        isDemo && m.localDemo
          ? 'Demo invitation copied. Each browser has an independent scripted demo.'
          : 'Invitation link copied.',
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
    try {
      const updated = await updateParticipant(m, { language: next });
      app.setMembership({
        ...m,
        participant: { ...m.participant, ...(updated as object), language: next },
      });
      app.setPreferences({ language: next });
      dispatch(
        demoEvent('participant.updated', { participant: { ...m.participant, language: next } }),
      );
      setToast(`Listening language changed to ${languageName(next)}.`);
    } catch (e) {
      setError((e as Error).message);
    }
  };
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
  ) => (
    <button
      className={`meeting-tool ${active ? 'tool-active' : ''}`}
      title={label}
      aria-label={label}
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
            <span>{connection}</span>
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
            Listening in <strong>{languageName(language)}</strong>
          </span>
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
              <span>A little closer. In every language.</span>
            </div>
            <Badge tone="dark">
              <Users size={11} />
              {participants.length} in this space
            </Badge>
          </div>
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
          {(error || audio.error || state.error) && (
            <div className="meeting-error" role="alert">
              <span>{error || audio.error || state.error}</span>
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
              />
            ))}
          </div>
          {participants.length === 1 && (
            <div className="waiting-note">
              <Link2 size={17} />
              <div>
                <strong>There’s room for another perspective.</strong>
                <p>Invite a participant who speaks a different language to begin.</p>
              </div>
              <button onClick={() => void copyInvite()}>
                Copy invitation
                <Copy size={13} />
              </button>
            </div>
          )}
          <div className={`caption-space ${captions ? 'captions-on' : ''}`}>
            {captions && latest ? (
              <div className="live-caption">
                <span>
                  {isDemo ? 'EXAMPLE · ' : ''}
                  {latest.speaker_name}
                </span>
                <p>
                  {latest.source_language === language
                    ? latest.text
                    : latest.translations[language] ||
                      'Translation not available in your language.'}
                </p>
              </div>
            ) : captions ? (
              <span className="caption-placeholder">
                {isDemo
                  ? 'Your example captions will appear here.'
                  : 'Captions will appear when a speech turn is ready.'}
              </span>
            ) : (
              <span className="caption-placeholder">Captions are off.</span>
            )}
          </div>
          <div className="meeting-stage-foot">
            <span>
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
          <aside className="meeting-side-panel">
            <div className="meeting-panel-heading">
              <h2>
                {panel === 'transcript'
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
            {panel === 'transcript' ? (
              <TranscriptPanel
                turns={state.turns}
                language={language}
                selfId={m.participant.id}
                onConfirm={confirm}
                onSubmit={submit}
                demo={isDemo}
                submitting={submitting}
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
                  onChange={(next) => void changeLanguage(next)}
                  label="I speak and want to hear"
                  id="meeting-language"
                />
                <p className="source-note">
                  Changing language reconnects translated audio subscriptions.
                </p>
                <div className="divider" />
                <h3>Your voice</h3>
                <div className="meeting-voice-select">
                  <AudioLines size={19} />
                  <div>
                    <strong>
                      {m.participant.voice_mode === 'cloned' ? 'Personal voice' : 'Standard voice'}
                    </strong>
                    <small>
                      {m.participant.voice_mode === 'cloned'
                        ? 'Consent-based session profile'
                        : 'Available without enrollment'}
                    </small>
                  </div>
                </div>
                <button
                  className="button secondary full"
                  onClick={() => {
                    void (audio.muted ? Promise.resolve() : audio.toggleMic()).then(() =>
                      setEnroll(true),
                    );
                  }}
                >
                  {app.voiceProfile ? 'Manage voice profile' : 'Enroll my voice'}
                </button>
                <div className="divider" />
                <h3>Audio playback</h3>
                <p className="source-note">{audio.status}</p>
                <button
                  className="button secondary full"
                  style={{ marginTop: 12 }}
                  onClick={() => void audio.unlock()}
                >
                  <Volume2 size={15} />
                  Enable speaker
                </button>
                {!isDemo && (
                  <button
                    className="button ghost full"
                    style={{ marginTop: 8 }}
                    onClick={audio.retry}
                  >
                    <RotateCcw size={14} />
                    Reconnect audio
                  </button>
                )}
                <div className="divider" />
                <h3>Keyboard shortcuts</h3>
                <div className="shortcut-row">
                  <span>Toggle microphone</span>
                  <kbd>M</kbd>
                </div>
                <div className="shortcut-row">
                  <span>Toggle captions</span>
                  <kbd>C</kbd>
                </div>
              </div>
            ) : (
              <div className="side-panel-content">
                <span className="feature-icon green">
                  <AudioLines size={21} />
                </span>
                <h3 style={{ marginTop: 16 }}>{room.title}</h3>
                <p className="panel-intro">
                  {isDemo
                    ? 'A space to explore the experience using scripted examples.'
                    : 'A shared audio room with language-specific interpretation.'}
                </p>
                <div className="divider" />
                <label className="field">
                  <span>Invitation link</span>
                  <input value={invitation} readOnly onFocus={(e) => e.target.select()} />
                </label>
                <button className="button primary full" onClick={() => void copyInvite()}>
                  <Copy size={14} />
                  Copy invitation
                </button>
                <div className="divider" />
                <h3>How this room works</h3>
                <ol className="room-howto">
                  <li>Choose the language you speak and want to hear.</li>
                  <li>
                    {isDemo
                      ? 'Start the fixed sample script.'
                      : 'Your microphone is routed to the interpretation agent.'}
                  </li>
                  <li>
                    {isDemo
                      ? 'Read the example in the conversation panel.'
                      : 'Hear translated speech addressed to your language.'}
                  </li>
                  <li>Confirm your understanding of important details.</li>
                </ol>
                <button className="button secondary full" onClick={reconnect}>
                  <RotateCcw size={14} />
                  Reconnect events
                </button>
              </div>
            )}
          </aside>
        )}
      </div>
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
            isDemo ? 'Demo mic off' : audio.muted ? 'Unmute' : 'Mute',
            audio.muted ? <MicOff size={20} /> : <Mic size={20} />,
            () => void audio.toggleMic(),
            !audio.muted,
            audio.working || isDemo,
          )}
          {tool(
            audio.outputMuted ? 'Speaker off' : 'Speaker',
            audio.outputMuted ? <VolumeX size={20} /> : <Volume2 size={20} />,
            audio.toggleOutput,
            !audio.outputMuted,
          )}
          <span className="toolbar-divider" />
          {tool('Captions', <Captions size={20} />, () => setCaptions(!captions), captions)}
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
      {enroll && (
        <Modal title="Your own voice, with your permission." onClose={() => setEnroll(false)} wide>
          <p className="muted">
            Record 5–30 seconds of your own speech. Voice enrollment is optional.
          </p>
          <VoiceEnrollment />
        </Modal>
      )}
    </div>
  );
}
