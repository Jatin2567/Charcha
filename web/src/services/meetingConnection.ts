import type { Membership } from '../types/domain';
import { request } from './api';

/** Media join tokens are short-lived; a saved seat is not a reusable media token. */
export async function refreshMeetingConnection(m: Membership, signal?: AbortSignal): Promise<Membership> {
  if (m.localDemo || m.room.mode === 'demo') return m;
  const next = await request<Membership>(`/rooms/${encodeURIComponent(m.room.code)}/connection`,
    { method: 'POST', signal }, m.session_token);
  if (signal?.aborted) throw new DOMException('Connection cancelled', 'AbortError');
  if (next?.room?.code !== m.room.code || next?.participant?.id !== m.participant.id ||
      next.session_token !== m.session_token || !next.livekit?.token || !next.livekit.url ||
      !next.livekit.agent_identity)
    throw new Error('Meeting access could not be restored. Reconnect or return to the invitation.');
  return next;
}
