/** Automatic decoded-audio observations, never proof of physical speaker playback. */
export const LATENCY_TOPIC = 'charcha.latency.v1';
const MAX_CLOCK_AGE = 60000;
const MAX_POLL_GAP = 300;
const QUIET_MS = 150;
const ENERGY_THRESHOLD = 0.006;
const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n) && n >= 0;
const identifier = (s: unknown): s is string => typeof s === 'string' && s.length > 0 && s.length <= 128;

export interface TurnMarker {
  marker_id: string;
  utterance_id: string;
  speaker_id: string;
  target_language: string;
  track_name: string;
  source_end_server_ms: number | null;
  source_boundary: 'server_ingress_energy_end';
  published_server_ms: number;
}
export interface ClockReply { clock_id: string; server_ms: number; expires_in_ms: number }
interface Clock { id: string; offset: number; rtt: number; received: number; expires: number }
export type ObservationStatus = 'detected' | 'ambiguous' | 'muted' | 'blocked' | 'timeout';
export interface TurnObservation {
  marker_id: string;
  status: ObservationStatus;
  observed_server_ms: number | null;
  clock_id: string | null;
  clock_rtt_ms: number | null;
  clock_age_ms: number | null;
  poll_interval_ms: number;
}
type TrackState = { at: number; quietSince: number | null; lastEnergy: number | null; playing: boolean };
type Pending = { marker: TurnMarker; received: number };

export function turnMarker(value: unknown, language: string, self: string): TurnMarker | null {
  if (!value || typeof value !== 'object') return null;
  const v = value as TurnMarker;
  if (!identifier(v.marker_id) || !identifier(v.utterance_id) || !identifier(v.speaker_id) ||
      v.speaker_id === self || v.target_language !== language ||
      v.track_name !== `translated:${v.speaker_id}:${language}` ||
      v.source_boundary !== 'server_ingress_energy_end' || !finite(v.published_server_ms) ||
      (v.source_end_server_ms !== null && (!finite(v.source_end_server_ms) || v.source_end_server_ms > v.published_server_ms))) return null;
  return v;
}

export class TurnLatencyTracker {
  private clock: Clock | null = null;
  private tracks = new Map<string, TrackState>();
  private pending = new Map<string, Pending>();
  private seen = new Set<string>();

  calibrate(reply: ClockReply, sent: number, received: number) {
    if (!identifier(reply.clock_id) || !finite(reply.server_ms) || !finite(sent) || !finite(received) ||
        received < sent || received - sent > 1000 || !finite(reply.expires_in_ms) || reply.expires_in_ms < 1) return false;
    const rtt = received - sent;
    // Keep the best recent probe, renewing before its server-issued lease expires.
    if (this.clock && received < this.clock.expires - 15000 && rtt > this.clock.rtt) return false;
    this.clock = { id: reply.clock_id, offset: reply.server_ms - (sent + received) / 2, rtt,
      received, expires: received + Math.min(MAX_CLOCK_AGE, reply.expires_in_ms) - rtt };
    return true;
  }

  private report(marker: TurnMarker, status: ObservationStatus, at: number, interval = 100): TurnObservation {
    const clock = this.clock;
    if (status === 'detected' && interval > 500) status = 'ambiguous';
    if (status === 'detected' && (!clock || at >= clock.expires || at < clock.received)) status = 'ambiguous';
    const serverAt = status === 'detected' && clock ? at + clock.offset : null;
    if (serverAt !== null && (serverAt < marker.published_server_ms ||
        marker.source_end_server_ms !== null && serverAt - marker.source_end_server_ms > 120000)) status = 'ambiguous';
    return { marker_id: marker.marker_id, status,
      observed_server_ms: status === 'detected' ? serverAt : null,
      clock_id: status === 'detected' && clock ? clock.id : null,
      clock_rtt_ms: status === 'detected' && clock ? clock.rtt : null,
      clock_age_ms: status === 'detected' && clock ? at - clock.received : null,
      poll_interval_ms: Math.min(500, Math.max(10, interval)) };
  }

  accept(marker: TurnMarker, at: number, unavailable?: 'muted' | 'blocked'): TurnObservation[] {
    if (this.seen.has(marker.marker_id)) return [];
    this.seen.add(marker.marker_id);
    if (this.seen.size > 256) this.seen.delete(this.seen.values().next().value!);
    const replies: TurnObservation[] = [];
    const previous = this.pending.get(marker.track_name);
    if (previous) replies.push(this.report(previous.marker, 'ambiguous', at));
    this.pending.delete(marker.track_name);
    const state = this.tracks.get(marker.track_name);
    const clock = this.clock;
    // A delayed data packet must not mistake a later pause inside the same audio
    // for the silence before that audio began. Media and data are not synchronized.
    const audioAlreadyObserved = !!clock && state?.lastEnergy != null &&
      state.lastEnergy + clock.offset >= marker.published_server_ms - clock.rtt / 2;
    if (unavailable) replies.push(this.report(marker, unavailable, at));
    else if (audioAlreadyObserved || !state?.playing || at - state.at > MAX_POLL_GAP || state.quietSince === null || at - state.quietSince < QUIET_MS)
      replies.push(this.report(marker, 'ambiguous', at));
    else this.pending.set(marker.track_name, { marker, received: at });
    return replies;
  }

  observe(track: string, rms: number, at: number, playing: boolean, fftWindowMs = 0): TurnObservation[] {
    const old = this.tracks.get(track);
    const gap = old ? at - old.at : 100;
    const quiet = finite(rms) && rms < ENERGY_THRESHOLD;
    this.tracks.set(track, { at, playing, lastEnergy: !quiet && playing ? at : old?.lastEnergy ?? null, quietSince: quiet && playing
      ? old?.playing && old.quietSince !== null && gap <= MAX_POLL_GAP ? old.quietSince : at : null });
    const pending = this.pending.get(track);
    if (!pending) return [];
    let status: ObservationStatus | null = null;
    if (!playing) status = 'blocked';
    else if (!finite(rms) || gap > MAX_POLL_GAP || gap < 0 || !finite(fftWindowMs)) status = 'ambiguous';
    else if (at - pending.received > 30000) status = 'timeout';
    else if (!quiet) status = 'detected';
    if (!status) return [];
    this.pending.delete(track);
    return [this.report(pending.marker, status, at, gap + fftWindowMs)];
  }

  interrupt(at: number, status: 'muted' | 'blocked' = 'blocked'): TurnObservation[] {
    const reports = [...this.pending.values()].map(({ marker }) => this.report(marker, status, at));
    this.pending.clear();
    this.tracks.clear();
    return reports;
  }
}
