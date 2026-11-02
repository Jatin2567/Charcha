import { describe, expect, it } from 'vitest';
import { isProbeChallenge, ProbeSignalTracker, probeTrackForListener, type ProbeChallenge } from './audioProbe';

const challenge: ProbeChallenge = {
  probe_id: 'unique_probe_123456789012', listener_id: 'listener-1',
  track_name: 'probe:unique_probe_123456789012:listener-1',
  measurement: 'request_to_decoded_probe_audio', expires_in_ms: 30000,
};

describe('dedicated local RTC audio probe', () => {
  it('validates exact listener, dedicated track and bounded challenge expiry', () => {
    expect(isProbeChallenge(challenge, 'listener-1')).toBe(true);
    expect(isProbeChallenge(challenge, 'listener-2')).toBe(false);
    expect(isProbeChallenge({ ...challenge, track_name: 'raw:source:all' }, 'listener-1')).toBe(false);
    expect(isProbeChallenge({ ...challenge, expires_in_ms: Infinity }, 'listener-1')).toBe(false);
    expect(isProbeChallenge({ ...challenge, expires_in_ms: 0 }, 'listener-1')).toBe(false);
    expect(probeTrackForListener(challenge.track_name, 'listener-1')).toBe(true);
    expect(probeTrackForListener(challenge.track_name, 'listener-2')).toBe(false);
    expect(probeTrackForListener('probe:short:listener-1', 'listener-1')).toBe(false);
  });

  it('measures one browser clock, only after two distinct audible-track observations', () => {
    let now = 1000;
    const tracker = new ProbeSignalTracker(challenge, () => now);
    expect(tracker.observe(challenge.track_name, 0.1, true)).toBeNull();
    tracker.start();
    now += 150;
    expect(tracker.observe(challenge.track_name, 0.1, true)).toBeNull();
    expect(tracker.observe(challenge.track_name, 0.1, true)).toBeNull();
    now += 100;
    expect(tracker.observe(challenge.track_name, 0.1, true)).toEqual({
      probe_id: challenge.probe_id, status: 'detected', elapsed_ms: 250,
      poll_interval_ms: 100, output_enabled: true,
    });
    now += 100;
    expect(tracker.observe(challenge.track_name, 0.1, true)).toBeNull();
    expect(tracker.timeout()).toBeNull();
  });

  it('ignores other tracks, silence, malformed levels and disabled output', () => {
    let now = 100;
    const tracker = new ProbeSignalTracker(challenge, () => now);
    tracker.start();
    for (const [track, level, enabled] of [
      ['raw:source:all', 0.5, true],
      [challenge.track_name, 0, true],
      [challenge.track_name, NaN, true],
      [challenge.track_name, Infinity, true],
      [challenge.track_name, 0.5, false],
    ] as const) {
      now += 100;
      expect(tracker.observe(track, level, enabled)).toBeNull();
    }
    now += 100;
    expect(tracker.observe(challenge.track_name, 0.5, true)).toBeNull();
    now += 100;
    expect(tracker.observe(challenge.track_name, 0, true)).toBeNull();
    now += 100;
    expect(tracker.observe(challenge.track_name, 0.5, true)).toBeNull();
    now += 100;
    expect(tracker.observe(challenge.track_name, 0.5, true)?.status).toBe('detected');
  });

  it('returns no latency for timeout, cancellation or a broken monotonic clock', () => {
    let now = 100;
    const timedOut = new ProbeSignalTracker(challenge, () => now);
    timedOut.start();
    now += 30001;
    expect(timedOut.observe(challenge.track_name, 0.5, true)).toMatchObject({ status: 'timeout', elapsed_ms: null });
    const cancelled = new ProbeSignalTracker(challenge, () => now);
    cancelled.start();
    expect(cancelled.cancel()).toMatchObject({ status: 'cancelled', elapsed_ms: null });
    expect(cancelled.cancel()).toBeNull();
    const reversed = new ProbeSignalTracker(challenge, () => now);
    reversed.start();
    now -= 1;
    expect(reversed.observe(challenge.track_name, 0.5, true)).toMatchObject({ status: 'cancelled', elapsed_ms: null });
  });

  it('does not restart probes or accept invalid configuration', () => {
    const tracker = new ProbeSignalTracker(challenge, () => 10);
    tracker.start();
    expect(() => tracker.start()).toThrow('already started');
    expect(() => new ProbeSignalTracker(challenge, () => 10, 0)).toThrow('sampling interval');
    expect(() => new ProbeSignalTracker({ ...challenge, probe_id: 'bad' })).toThrow('Invalid audio probe');
    expect(() => new ProbeSignalTracker(challenge, () => NaN).start()).toThrow('monotonic clock');
  });
});
