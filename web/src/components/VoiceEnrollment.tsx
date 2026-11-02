import { useRef, useState } from 'react';
import { Mic, Square, Upload, Trash2, Check, AudioLines } from 'lucide-react';
import { useVoiceRecorder } from '../hooks/useVoiceRecorder';
import { useApp } from '../state/AppContext';
import { deleteVoice, updateParticipant, uploadVoice } from '../services/api';
import { ErrorNotice, Badge } from './ui';
import { Link } from 'react-router-dom';
export function VoiceEnrollment({ onSuccess }: { onSuccess?: () => void }) {
  const app = useApp();
  const recorder = useVoiceRecorder();
  const [consent, setConsent] = useState(false);
  const [name, setName] = useState('My conversation voice');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const file = useRef<HTMLInputElement>(null);
  const profile = app.voiceProfile;
  if (app.health?.mode === 'transport' || app.membership?.room.mode === 'transport')
    return <div className="notice warning"><span>Voice cloning is disabled during local audio tests. Complete the interpretation and device checks in <Link to="/tests">Test lab</Link> first.</span></div>;
  const enroll = async () => {
    if (!app.membership || !recorder.blob || !consent) return;
    setBusy(true);
    setError('');
    try {
      const p = await uploadVoice(recorder.blob, name, app.membership);
      app.setVoiceProfile(p);
      if (p.mode === 'live') {
        const participant = await updateParticipant(app.membership, {
          voice_mode: 'cloned',
          voice_profile_id: p.id,
        });
        app.setMembership({
          ...app.membership,
          participant: participant as typeof app.membership.participant,
        });
      }
      setSuccess(
        p.mode === 'demo'
          ? 'Demo enrollment complete. No voice cloning was performed.'
          : 'Voice enrolled. Your room now uses your personal voice.',
      );
      recorder.clear();
      onSuccess?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!profile || !app.membership) return;
    setBusy(true);
    try {
      await deleteVoice(profile.id, app.membership);
      if (profile.mode === 'live') {
        const participant = await updateParticipant(app.membership, { voice_mode: 'standard' });
        app.setMembership({
          ...app.membership,
          participant: participant as typeof app.membership.participant,
        });
      }
      app.setVoiceProfile(null);
      setSuccess('Voice profile deleted. Standard voice is selected.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="voice-enrollment">
      {profile ? (
        <div className="enrolled-profile">
          <span className="feature-icon green">
            <AudioLines size={21} />
          </span>
          <div>
            <strong>{profile.name}</strong>
            <small>
              {profile.mode === 'demo'
                ? 'Demo profile · no actual cloning'
                : 'Session voice profile'}
            </small>
          </div>
          <Badge tone={profile.mode === 'demo' ? 'orange' : 'green'}>
            {profile.mode === 'demo' ? 'Demo' : 'Enrolled'}
          </Badge>
          <button
            className="icon-button"
            aria-label="Delete my voice profile"
            disabled={busy}
            onClick={() => void remove()}
          >
            <Trash2 size={17} />
          </button>
        </div>
      ) : (
        <>
          <label className="field">
            <span>Voice profile name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
          </label>
          <div className={`recording-station ${recorder.recording ? 'is-recording' : ''}`}>
            <span className="recording-icon">
              <Mic size={30} strokeWidth={1.5} />
            </span>
            <div className="recording-time">
              {Math.floor(recorder.duration).toString().padStart(2, '0')}
              <span> / 30 sec</span>
            </div>
            <div className="recording-progress">
              <i style={{ width: `${(recorder.duration / 30) * 100}%` }} />
            </div>
            <p>
              {recorder.recording
                ? 'Speak clearly in your everyday voice.'
                : recorder.blob
                  ? 'Your reference is ready to review.'
                  : 'Find a quiet place. Your own voice is all you need.'}
            </p>
            <button
              className={`button ${recorder.recording ? 'danger' : 'primary'}`}
              disabled={recorder.pending}
              onClick={() =>
                recorder.recording
                  ? recorder.stop()
                  : void recorder.start(app.preferences.inputDevice)
              }
            >
              {recorder.recording ? <Square size={14} /> : <Mic size={16} />}{' '}
              {recorder.pending
                ? 'Waiting for microphone…'
                : recorder.recording
                  ? 'Stop recording'
                  : recorder.blob
                    ? 'Record again'
                    : 'Start recording'}
            </button>
            {!recorder.recording && (
              <button className="text-link" onClick={() => file.current?.click()}>
                <Upload size={13} />
                Or upload a 5–30 second reference
              </button>
            )}
            <input
              ref={file}
              type="file"
              accept="audio/wav,audio/x-wav,.wav"
              className="sr-only"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void recorder.loadFile(f);
                e.target.value = '';
              }}
            />
          </div>
          {recorder.url && (
            <div className="audio-review">
              <audio
                controls
                src={recorder.url}
                aria-label="Preview your recorded voice reference"
              />
              <button
                className="icon-button"
                aria-label="Delete reference recording"
                onClick={recorder.clear}
              >
                <Trash2 size={17} />
              </button>
            </div>
          )}
          <label className="check-line">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <span>
              I am enrolling my own voice. I consent to using this reference to create interpreted
              speech for this session.
            </span>
          </label>
          {!app.membership && (
            <div className="notice info">
              Join a conversation first to create a session-scoped voice profile. You can record and
              preview a reference here.
            </div>
          )}
          <button
            className="button primary full"
            disabled={
              !app.membership ||
              !recorder.blob ||
              recorder.duration < 5 ||
              recorder.duration > 30 ||
              !consent ||
              busy ||
              !name.trim()
            }
            onClick={() => void enroll()}
          >
            <Check size={16} />
            {busy
              ? 'Enrolling voice…'
              : app.membership?.room.mode === 'demo'
                ? 'Try demo enrollment'
                : 'Enroll my voice'}
          </button>
          <p className="source-note">
            5–30 seconds of clean, spoken audio. The server creates a session-scoped embedding and
            discards the raw reference. Demo mode never clones your voice.
          </p>
        </>
      )}
      <ErrorNotice message={error || recorder.error} />
      {success && (
        <div className="notice info" role="status">
          <Check size={16} />
          {success}
        </div>
      )}
    </div>
  );
}
