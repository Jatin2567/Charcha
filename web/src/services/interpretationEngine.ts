import { request } from './api';
import type { Membership } from '../types/domain';

export type EngineStatus = {
  state: 'idle' | 'starting' | 'ready' | 'unavailable' | 'external';
  startup_ms?: number | null;
  elapsed_ms?: number | null;
  observed_at?: string | null;
  lifecycle?: 'meeting' | 'request';
  active_meetings?: number;
};
export const engineStatus = (m?: Membership) =>
  request<EngineStatus>(m ? `/rooms/${m.room.code}/engine` : '/account/interpretation-engine', {}, m?.session_token);

// Poll only our local API state. These GETs never wake or keep the GPU alive.
export async function ensureEngine(m: Membership, isCurrent: () => boolean) {
  if (!m.room.engine_on_demand) return;
  let status = await engineStatus(m);
  // Occupied meetings already maintain readiness; normal unmute must not spend
  // a retry/start allowance on every turn. POST only nudges startup or recovery.
  if (status.state === 'idle' || status.state === 'unavailable' ||
      (status.lifecycle === 'meeting' && !status.active_meetings))
    status = await request<EngineStatus>(`/rooms/${m.room.code}/engine`, { method: 'POST' }, m.session_token);
  const deadline = Date.now() + 910_000;
  while (isCurrent()) {
    if (status.state === 'ready') return;
    if (status.state === 'unavailable' || Date.now() > deadline)
      throw new Error('Interpretation could not start. Check availability and try unmuting again.');
    await new Promise((resolve) => setTimeout(resolve, 2000));
    if (!isCurrent()) break;
    status = await engineStatus(m);
  }
  throw new Error('Meeting changed while interpretation was starting.');
}
