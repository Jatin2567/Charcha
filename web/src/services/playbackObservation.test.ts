import { describe, expect, it } from 'vitest';
import { playbackObservation } from './playbackObservation';

const record = {
  schema_version: 1,
  recording_sha256: '1'.repeat(64),
  observation_id: '2'.repeat(64),
  record_type: 'speech_end_playback_observation',
  clock: 'single_recording_sample_index',
  boundary: 'source_speech_end_to_listener_output',
  status: 'complete',
  provider_kind: 'live',
  voice_mode: 'standard',
  voice_cloning: false,
  physical_playback_measured: true,
  capture_attested: true,
  annotations_reviewed: true,
  capture_provenance: 'operator_attested',
  provider_provenance: 'operator_attested',
  meaning_reviewed: false,
  capture_kind: 'acoustic_single_channel',
  recording_channels: 1,
  source_channel_index: 0,
  listener_channel_index: 0,
  screening_mode: 'monitor',
  condition: 'first_route',
  source_language: 'hi',
  target_language: 'ta',
  sample_rate_hz: 16000,
  recording_frames: 48000,
  source_speech_end_sample: 16000,
  listener_audio_start_sample: 24000,
  latency_ms: 500,
};

describe('physical playback observations', () => {
  it('keeps capture mode, screening and human review with the measured offset', () => {
    expect(playbackObservation(record)).toMatchObject({
      latency: 500,
      screening: 'monitor',
      meaningReviewed: false,
    });
    expect(
      playbackObservation({ ...record, listener_audio_start_sample: 14400, latency_ms: -100 })
        ?.latency,
    ).toBe(-100);
  });
  it.each([
    { latency_ms: 499 },
    { recording_sha256: '' },
    { capture_attested: false },
    { provider_kind: 'double' },
    { source_language: 'ta' },
    { capture_kind: 'browser_render_dual_channel' },
    { sample_rate_hz: 0 },
    { recording_channels: 2 },
    { listener_audio_start_sample: null },
    { meaning_reviewed: 'true' },
    { screening_mode: 'unknown' },
  ])('rejects inconsistent or unreviewed physical measurements', (change) => {
    expect(playbackObservation({ ...record, ...change })).toBeNull();
  });
});
