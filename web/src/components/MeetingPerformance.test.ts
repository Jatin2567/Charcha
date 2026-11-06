import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { MeetingPerformance } from './MeetingPerformance';
import { emptyPerformance } from '../services/performance';
import type { Membership } from '../types/domain';
import type { PerformanceSample } from '../types/performance';

const hooks = vi.hoisted(() => ({ performance: vi.fn(), network: vi.fn() }));
vi.mock('../hooks/usePerformance', () => ({ usePerformance: hooks.performance }));
vi.mock('../hooks/useTransportMetrics', () => ({ useTransportMetrics: hooks.network }));

const member: Membership = {
  room: {
    id: 'room',
    code: 'room',
    title: 'Meeting',
    created_at: '',
    mode: 'live',
    participants: [],
  },
  participant: {
    id: 'p',
    name: 'Listener',
    language: 'ta',
    voice_mode: 'standard',
    muted: true,
    is_agent: false,
    is_demo: false,
    joined_at: '',
  },
  session_token: 'fixture',
  livekit: null,
};
const audio: PerformanceSample = {
  id: 'a',
  utterance_id: 'u',
  source_language: 'hi',
  target_language: 'ta',
  input_kind: 'audio',
  voice_mode: 'standard',
  status: 'complete',
  measurement: 'server_first_pcm',
  queue_ms: 0,
  stt_ms: 100,
  mt_ms: 200,
  tts_first_pcm_ms: 300,
  total_ms: 600,
  created_at: '',
};
type Check = Parameters<typeof MeetingPerformance>[0]['speakerCheck'];
const speakerCheck: Check = {
  connected: true,
  playback: 'ready',
  working: false,
  result: null,
  run: () => {},
};
function render(code: string, samples: PerformanceSample[], check: Check = speakerCheck) {
  hooks.performance.mockReturnValue({
    report: { ...emptyPerformance(code, 'live'), samples },
    error: '',
  });
  return renderToStaticMarkup(
    createElement(MeetingPerformance, {
      membership: member,
      onOpenReport: () => {},
      speakerCheck: check,
    }),
  );
}

describe('in-call performance', () => {
  it('offers the private tone only when speaker playback is usable', () => {
    const html = render('room', [], { ...speakerCheck, playback: 'blocked' });
    expect(html).toMatch(/<button[^>]*disabled[^>]*>Play test tone/);
    expect(html).toContain('Enable your speaker');
    expect(render('room', [])).not.toMatch(/<button[^>]*disabled[^>]*>Play test tone/);
  });
  it('separates linguistic deliveries from typed turns and shows real zero packet loss', () => {
    hooks.network.mockReturnValue({ network_rtt_ms: 31, jitter_ms: null, packet_loss_percent: 0 });
    const html = render('room', [audio, { ...audio, input_kind: 'text', total_ms: 9000 }]);
    expect(html).toContain('600 ms');
    expect(html).not.toContain('9000 ms');
    expect(html).toContain('Hindi → Tamil');
    expect(html).toContain('31 ms');
    expect(html).toContain('0.0%');
  });
  it('shows unavailable measurements while switching rooms', () => {
    hooks.network.mockReturnValue(null);
    const html = render('previous-room', [audio]);
    expect(html).toContain('Waiting for a completed spoken translation');
    expect(html).not.toContain('600 ms');
    expect(html).not.toContain('Last report');
    expect(html).not.toContain('0.0%');
  });
});
