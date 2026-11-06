import { useState } from 'react';
import { type Turn, languageName } from '../types/domain';

export function TurnCorrection({
  turn,
  onCorrect,
}: {
  turn: Turn;
  onCorrect: (turn: Turn, text: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState('');
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  return editing === turn.id ? (
    <form
      className="correction-editor"
      onSubmit={async (e) => {
        e.preventDefault();
        if (sending || !draft.trim()) return;
        setSending(true);
        setError('');
        try {
          await onCorrect(turn, draft.trim());
          setEditing('');
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Could not share this correction.');
        } finally {
          setSending(false);
        }
      }}
    >
      <label>
        What did you mean?{' '}
        <small>Write the full message in {languageName(turn.source_language)}.</small>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={2000}
          required
          autoFocus
        />
      </label>
      <small>
        Your earlier words stay in the transcript. Everyone can confirm the updated message.
      </small>
      {error && <p role="alert">{error}</p>}
      <button disabled={sending || !draft.trim() || draft.trim() === turn.text}>
        {sending ? 'Sharing…' : 'Share correction'}
      </button>
      <button type="button" disabled={sending} onClick={() => setEditing('')}>
        Cancel
      </button>
    </form>
  ) : (
    <button
      className="caption-confirm-btn"
      onClick={() => {
        setEditing(turn.id);
        setDraft(turn.text);
        setError('');
      }}
    >
      Correct for everyone
    </button>
  );
}
