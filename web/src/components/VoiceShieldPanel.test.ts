import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { VoiceShieldPanel } from './VoiceShieldPanel';
import {
  activeScreeningSamples,
  hasVoiceFlag,
  shieldingState,
  screeningMetric,
  screeningResultLabel,
} from '../services/voiceShield';
import type { RoomScreeningSample, RoomScreeningStatus } from '../services/localDiagnostics';
import type { Participant } from '../types/domain';

const sample: RoomScreeningSample = {
  speaker_id: 'speaker',
  verdict: 'allow',
  score: 0.12,
  compute_ms: 20,
  audio_window_ms: 4037.5,
  queue_ms: 1,
  hold_ms: 0,
  status: 'assessed',
  action: 'observed',
  mode: 'monitor',
  created_at: '2026-10-31T00:00:00Z',
  reasons: [],
};
const participant: Participant = {
  id: 'speaker',
  name: 'Example person',
  language: 'hi',
  voice_mode: 'standard',
  muted: false,
  is_agent: false,
  is_demo: false,
  joined_at: '2026-10-31T00:00:00Z',
};
const status: RoomScreeningStatus = {
  mode: 'monitor',
  model: {
    id: 'aasist',
    kind: 'onnx_classifier',
    revision: 'fixture',
    sha256: 'fixture',
    ready: true,
    license: 'MIT',
    validated_on_indian_meeting_audio: false,
    window_ms: 4037.5,
    threshold: 0.8,
    allow_threshold: 0.2,
  },
};
const render = (
  samples: Record<string, RoomScreeningSample> = {},
  connected = true,
  demo = false,
) =>
  renderToStaticMarkup(
    createElement(VoiceShieldPanel, {
      samples,
      participants: [participant],
      connected,
      status,
      demo,
    }),
  );

describe('live VoiceShield observations', () => {
  it('keeps failed, unknown and disabled assessments distinct from no flag', () => {
    expect(screeningResultLabel(sample)).toBe('No flag');
    expect(screeningResultLabel({ ...sample, status: 'error' })).toBe('Assessment unavailable');
    expect(screeningResultLabel({ ...sample, status: 'overload' })).toBe('Assessment unavailable');
    expect(screeningResultLabel({ ...sample, verdict: 'unknown' })).toBe('Inconclusive');
    expect(screeningResultLabel({ ...sample, verdict: 'suspicious' })).toBe(
      'Possible synthetic voice',
    );
    expect(screeningResultLabel({ ...sample, mode: 'off' })).toBe('Screening off');
    expect(hasVoiceFlag({ ...sample, status: 'error', verdict: 'suspicious' })).toBe(false);
  });

  it('does not turn missing or invalid measurements into zero', () => {
    for (const value of [null, undefined, NaN, Infinity, -1])
      expect(screeningMetric(value)).toBe('Not measured');
    expect(screeningMetric(0)).toBe('0 ms');
    expect(screeningMetric(123.456)).toBe('123.46 ms');
    expect(screeningMetric(0.12, '')).toBe('0.12');
    expect(screeningMetric(0.799999, '')).toBe('0.799999');
  });

  it('reports model readiness and awaits actual audio without sample controls', () => {
    const html = render();
    expect(html).toContain('Monitoring audio');
    expect(html).toContain('Collecting audio');
    expect(html).toContain('Pending validation');
    expect(html).toContain('Not measured');
    expect(html).not.toContain('Preview warning');
    expect(html).not.toContain('Example person');
    expect(
      shieldingState({ ...status, model: { ...status.model, ready: false } }, true, false).label,
    ).toBe('Detector unavailable');
    expect(shieldingState(null, true, false).label).toBe('Status unavailable');
    expect(shieldingState({ ...status, mode: 'off' }, true, false).label).toBe('Screening off');
  });

  it('displays only original current participant observations', () => {
    const samples = { speaker: sample, departed: { ...sample, speaker_id: 'departed' } };
    const before = JSON.stringify(samples);
    const html = render(samples);
    expect(html).toContain('Example person');
    expect(html).toContain('No flag');
    expect(html).toContain('0.12');
    expect(html).not.toContain('departed');
    expect(JSON.stringify(samples)).toBe(before);
  });

  it('suppresses flags after disconnect, mute, policy changes, identity mismatch and in demos', () => {
    const samples = { speaker: { ...sample, verdict: 'suspicious' as const } };
    expect(render(samples, false)).toContain('Updates paused');
    expect(render(samples, false)).not.toContain('Possible synthetic voice');
    expect(render(samples, true, true)).toContain('Unavailable in demo');
    expect(render(samples, true, true)).not.toContain('Example person');
    for (const person of [
      { ...participant, muted: true },
      { ...participant, is_demo: true },
    ])
      expect(activeScreeningSamples(samples, [person], status, true)).toEqual([]);
    expect(
      activeScreeningSamples(samples, [participant], { ...status, mode: 'off' }, true),
    ).toEqual([]);
    expect(
      activeScreeningSamples(
        { speaker: { ...sample, speaker_id: 'outsider' } },
        [participant],
        status,
        true,
      ),
    ).toEqual([]);
  });

  it('offers review only for a real assessed flag and hides failed scores', () => {
    const html = render({ speaker: { ...sample, verdict: 'suspicious', score: 0.95 } });
    expect(html).toContain('Possible synthetic voice');
    expect(html).toContain('Review Example person');
    expect(html).toContain('0.95');
    const failed = render({ speaker: { ...sample, status: 'error', score: 0.777777 } });
    expect(failed).toContain('Assessment unavailable');
    expect(failed).not.toContain('0.777');
    expect(failed).not.toContain('Review Example person');
  });
});
