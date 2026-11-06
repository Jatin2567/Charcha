import { describe, expect, it } from 'vitest';
import { TurnLatencyTracker, turnMarker, type TurnMarker } from './turnLatency';

const marker: TurnMarker = { marker_id: 'marker-one', utterance_id: 'turn-one', speaker_id: 'speaker',
  target_language: 'ta', track_name: 'translated:speaker:ta', source_end_server_ms: 1500,
  source_boundary: 'server_ingress_energy_end', published_server_ms: 2000 };
function ready() {
  const t = new TurnLatencyTracker();
  t.calibrate({ clock_id: 'clock-one', server_ms: 1000, expires_in_ms: 60000 }, 0, 20);
  for (const at of [800, 900, 1000]) t.observe(marker.track_name, 0, at, true);
  return t;
}
describe('turn audio latency observations', () => {
  it('correlates a quiet-to-decoded-audio onset using the measured clock offset', () => {
    const t = ready();
    expect(t.accept(marker, 1020)).toEqual([]);
    const [r] = t.observe(marker.track_name, .03, 1100, true, 22);
    expect(r.status).toBe('detected');
    expect(r.observed_server_ms).toBe(2090);
    expect(r.clock_rtt_ms).toBe(20);
    expect(r.poll_interval_ms).toBe(122);
    expect(t.observe(marker.track_name, .03, 1200, true)).toEqual([]);
    expect(t.accept(marker, 1300)).toEqual([]);
  });
  it('rejects a marker received over previous audio rather than timing its next pause', () => {
    const t = ready();
    t.observe(marker.track_name, .05, 1010, true);
    expect(t.accept(marker, 1020)[0].status).toBe('ambiguous');
  });
  it('does not claim playback with expired synchronization, blocked audio, or throttled polling', () => {
    for (const [at, playing, expected] of [[1400, true, 'ambiguous'], [1100, false, 'blocked'], [62000, true, 'ambiguous']] as const) {
      const t = ready(); t.accept(marker, 1020);
      const [r] = t.observe(marker.track_name, .04, at, playing);
      expect(r.status).toBe(expected); expect(r.observed_server_ms).toBeNull();
      expect(r.poll_interval_ms).toBeLessThanOrEqual(500);
    }
    const t = ready();
    expect(t.accept(marker, 1020, 'muted')[0].status).toBe('muted');
  });
  it('rejects a late marker even if its audio has reached an internal quiet pause', () => {
    const t = ready();
    t.observe(marker.track_name, .05, 1050, true);
    for (const at of [1100, 1200, 1300]) t.observe(marker.track_name, 0, at, true);
    expect(t.accept(marker, 1400)[0].status).toBe('ambiguous');
  });
  it('accepts only matching listener routes and refuses impossible source clocks', () => {
    expect(turnMarker(marker, 'ta', 'listener')).toEqual(marker);
    expect(turnMarker(marker, 'hi', 'listener')).toBeNull();
    expect(turnMarker(marker, 'ta', 'speaker')).toBeNull();
    expect(turnMarker({ ...marker, source_end_server_ms: 3000 }, 'ta', 'listener')).toBeNull();
  });
  it('selects a lower RTT calibration and refreshes an aging lease', () => {
    const t = ready();
    expect(t.calibrate({ clock_id: 'slow', server_ms: 1100, expires_in_ms: 60000 }, 100, 300)).toBe(false);
    expect(t.calibrate({ clock_id: 'new', server_ms: 51000, expires_in_ms: 60000 }, 50000, 50040)).toBe(true);
  });
});
