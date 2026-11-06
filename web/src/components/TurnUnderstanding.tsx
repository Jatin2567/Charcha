import type { Participant, Turn } from '../types/domain';
import { understanding, turnRecovery } from '../services/turnUnderstanding';
import './TurnUnderstanding.css';

export function TurnUnderstanding({ turn, participants = [] }: { turn: Turn; participants?: Participant[] }) {
  const result = understanding(turn, participants);
  const pending = result.listeners.filter(p => !p.confirmed);
  return <details className="turn-understanding">
    <summary>{turn.superseded_by ? 'Earlier acknowledgements' : result.all ? 'All listed listeners confirmed understanding' : 'Who confirmed understanding?'}</summary>
    <ul>{result.listeners.map(p => <li key={p.id}><strong>{p.name}</strong> — {p.confirmed ? 'Confirmed understanding' : 'Not yet confirmed'}</li>)}
      {result.legacy.map(p => <li key={p.id}>{p.name} — Recorded acknowledgement; eligibility not verified</li>)}</ul>
    {!result.known && <p>Listener list not recorded. Full participation is unknown.</p>}
    {result.known && !result.listeners.length && <p>No other listeners were present for this message.</p>}
    {pending.length > 0 && !turn.superseded_by && <p>Waiting for {pending.map(p => p.name).join(', ')}</p>}
    <p>{turn.superseded_by ? 'Confirm the corrected message separately. ' : ''}Confirmation means understanding, not agreement or proof of accuracy. This list covers listeners present when the message was submitted; later arrivals are not included.</p>
  </details>;
}

export function TurnRecovery({ turn }: { turn: Turn }) {
  const recovery = turnRecovery(turn);
  return recovery ? <div className="turn-recovery" role="status"><strong>{recovery.title}</strong><p>{recovery.detail}</p></div> : null;
}
