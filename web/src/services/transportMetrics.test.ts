import { afterEach, describe, expect, it, vi } from 'vitest';
import { isTransportMetrics, openPerformancePage, transportMetrics } from './transportMetrics';

describe('browser media measurements', () => {
  it('keeps unsupported or absent statistics unavailable, including loss with no packets', () => {
    const result = transportMetrics([], 0);
    expect(result.network_rtt_ms).toBeNull();
    expect(result.packet_loss_percent).toBeNull();
    expect(result.jitter_buffer_ms).toBeNull();
    expect(isTransportMetrics(result)).toBe(true);
  });
  it('uses the selected media path, converts seconds, and deduplicates shared reports', () => {
    const audio = {
      id: 'audio',
      type: 'inbound-rtp',
      kind: 'audio',
      jitter: 0.005,
      jitterBufferDelay: 4,
      jitterBufferEmittedCount: 200,
      packetsReceived: 98,
      packetsLost: 2,
    };
    const result = transportMetrics(
      [
        { id: 'transport', type: 'transport', selectedCandidatePairId: 'chosen' },
        { id: 'chosen', type: 'candidate-pair', currentRoundTripTime: 0.04 },
        {
          id: 'other',
          type: 'candidate-pair',
          nominated: true,
          state: 'succeeded',
          currentRoundTripTime: 12,
        },
        audio,
        audio,
        { id: 'video', type: 'inbound-rtp', kind: 'video', packetsReceived: 10000, packetsLost: 0 },
      ],
      1,
    );
    expect(result.network_rtt_ms).toBe(40);
    expect(result.jitter_ms).toBe(5);
    expect(result.jitter_buffer_ms).toBe(20);
    expect(result.packet_loss_percent).toBe(2);
    expect(result.packets_received).toBe(98);
  });
  it('ignores invalid values and clamps negative late-packet loss', () => {
    const result = transportMetrics(
      [
        {
          id: 'audio',
          type: 'inbound-rtp',
          kind: 'audio',
          packetsReceived: 5,
          packetsLost: -2,
          jitter: NaN,
          jitterBufferDelay: 5,
          jitterBufferEmittedCount: 0,
        },
      ],
      1,
    );
    expect(result.packet_loss_percent).toBe(0);
    expect(result.jitter_ms).toBeNull();
    expect(result.jitter_buffer_ms).toBeNull();
    expect(isTransportMetrics({ ...result, packet_loss_percent: 101 })).toBe(false);
    expect(isTransportMetrics({ ...result, network_rtt_ms: Infinity })).toBe(false);
  });
});

describe('report tab isolation', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('copies room membership only to the same origin and removes the opener', () => {
    const setItem = vi.fn();
    const child = { sessionStorage: { setItem }, opener: {}, close: vi.fn() };
    const open = vi.fn(() => child);
    vi.stubGlobal('window', { open, location: { href: 'https://meeting.example/#/room/abc' } });
    vi.stubGlobal('sessionStorage', { getItem: vi.fn(() => 'scoped-membership') });
    expect(openPerformancePage('current-session')).toBe(true);
    expect(open).toHaveBeenCalledWith('https://meeting.example/#/performance', '_blank');
    expect(setItem).toHaveBeenCalledExactlyOnceWith('charcha.membership.current-session', 'scoped-membership');
    expect(child.opener).toBeNull();
  });
  it('handles popup denial without changing the original meeting', () => {
    const location = { href: 'http://localhost/#/room/abc' };
    vi.stubGlobal('window', { open: vi.fn(() => null), location });
    expect(openPerformancePage()).toBe(false);
    expect(location.href).toBe('http://localhost/#/room/abc');
  });
});
