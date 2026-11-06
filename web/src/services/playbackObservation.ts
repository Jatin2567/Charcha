import { LANGUAGES, type Language } from '../types/domain';

const language = (value: unknown): value is Language => LANGUAGES.some((row) => row.code === value);
const integer = (value: unknown): value is number =>
  typeof value === 'number' && Number.isSafeInteger(value);

/** Read only the reviewed live physical observation format produced by the offline WAV tool. */
export function playbackObservation(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  const rate = row.sample_rate_hz,
    frames = row.recording_frames;
  const end = row.source_speech_end_sample,
    start = row.listener_audio_start_sample;
  const mono = row.capture_kind === 'acoustic_single_channel';
  if (
    row.schema_version !== 1 ||
    row.record_type !== 'speech_end_playback_observation' ||
    typeof row.recording_sha256 !== 'string' ||
    !/^[0-9a-f]{64}$/.test(row.recording_sha256) ||
    typeof row.observation_id !== 'string' ||
    !/^[0-9a-f]{64}$/.test(row.observation_id) ||
    row.clock !== 'single_recording_sample_index' ||
    row.boundary !== 'source_speech_end_to_listener_output' ||
    row.status !== 'complete' ||
    row.provider_kind !== 'live' ||
    row.voice_mode !== 'standard' ||
    row.voice_cloning !== false ||
    row.physical_playback_measured !== true ||
    row.capture_attested !== true ||
    row.annotations_reviewed !== true ||
    row.capture_provenance !== 'operator_attested' ||
    row.provider_provenance !== 'operator_attested' ||
    typeof row.meaning_reviewed !== 'boolean' ||
    (!mono &&
      row.capture_kind !== 'acoustic_two_channel' &&
      row.capture_kind !== 'electrical_loopback_two_channel') ||
    row.recording_channels !== (mono ? 1 : 2) ||
    row.source_channel_index !== 0 ||
    row.listener_channel_index !== (mono ? 0 : 1) ||
    (row.screening_mode !== 'off' &&
      row.screening_mode !== 'monitor' &&
      row.screening_mode !== 'enforce') ||
    (row.condition !== 'first_route' && row.condition !== 'warm_route') ||
    !language(row.source_language) ||
    !language(row.target_language) ||
    row.source_language === row.target_language ||
    !integer(rate) ||
    rate < 8000 ||
    rate > 96000 ||
    !integer(frames) ||
    frames < 1 ||
    frames > 120 * rate ||
    !integer(end) ||
    end < 1 ||
    end > frames ||
    !integer(start) ||
    start < 0 ||
    start >= frames ||
    typeof row.latency_ms !== 'number' ||
    !Number.isFinite(row.latency_ms) ||
    Math.abs(row.latency_ms - ((start - end) * 1000) / rate) > 0.000051
  )
    return null;
  return {
    latency: row.latency_ms,
    source: row.source_language,
    target: row.target_language,
    condition: row.condition === 'first_route' ? 'First use' : 'Warmed up',
    capture:
      row.capture_kind === 'electrical_loopback_two_channel'
        ? 'Electrical loopback'
        : 'Acoustic recording',
    screening: row.screening_mode,
    meaningReviewed: row.meaning_reviewed,
  };
}
