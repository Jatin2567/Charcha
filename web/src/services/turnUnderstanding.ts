import type { Participant, Turn } from '../types/domain';

export function understanding(turn: Turn, participants: Participant[] = []) {
  const known = turn.listeners_recorded === true || !!turn.replaces_id;
  const confirmed = new Set(turn.confirmed_by);
  const listeners = Object.entries(turn.listeners || {}).map(([id, name]) => ({
    id, name, confirmed: confirmed.has(id),
  }));
  const legacy = [...confirmed].filter(id => !listeners.some(p => p.id === id)).map(id => ({
    id, name: participants.find(p => p.id === id)?.name || 'Participant ' + id.slice(0, 8),
  }));
  return { known, listeners, legacy,
    all: known && listeners.length > 0 && listeners.every(p => p.confirmed) && !turn.superseded_by && turn.status === 'complete',
  };
}

export function canConfirm(turn: Turn, selfId: string) {
  return understanding(turn).known && Object.hasOwn(turn.listeners || {}, selfId) &&
    !turn.superseded_by && turn.status === 'complete';
}

export function confirmationText(turn: Turn, participants: Participant[] = []) {
  const result = understanding(turn, participants);
  const lines = result.listeners.map(p => `${p.name}: ${p.confirmed ? 'confirmed understanding' : 'not yet confirmed'}`);
  lines.push(...result.legacy.map(p => `${p.name}: recorded acknowledgement (listener eligibility not verified)`));
  if (!result.known) lines.push('Listener list not recorded; full participation cannot be determined.');
  else if (!result.listeners.length) lines.push('No other listeners were present for this message.');
  if (turn.superseded_by) lines.push('Earlier version: confirmations do not carry over to the correction.');
  return lines.join('\n');
}

export function turnRecovery(turn: Turn) {
  if (turn.status !== 'error') return null;
  if (turn.recovery_reason === 'queue_expired') return {
    title: 'Interpretation fell behind',
    detail: 'This turn was not delivered completely. Its caption is kept. Pause for playback to finish, then repeat the missed phrase.',
  };
  if (turn.recovery_reason === 'interrupted') return {
    title: 'Interpretation interrupted',
    detail: 'Some listeners may have missed this turn. Once the room is connected, repeat the phrase or type it in the transcript.',
  };
  return { title: 'Interpretation incomplete',
    detail: 'Some listeners may have received only part of this turn. Review the captions, then ask the speaker to repeat or clarify. No automatic retry was made.' };
}
