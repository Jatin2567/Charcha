import { request } from './api';
import type {
  AudioScreenResult,
  AudioLabResponse,
  AudioLabStatus,
  DiagnosticFixture,
  ScreeningObservation,
  SharedRecordingObservation,
} from '../types/audioLab';

export const MAX_AUDIO_BYTES = 1_024_000;
export const MAX_AUDIO_SECONDS = 30;
const SAMPLE_RATE = 16_000;

function ascii(view: DataView, start: number, count: number) {
  return Array.from({ length: count }, (_, i) => String.fromCharCode(view.getUint8(start + i))).join('');
}

/** Header validation only; the server independently decodes and checks every upload. */
export function inspectScreeningWav(buffer: ArrayBuffer) {
  const { seconds, sample_rate, channels, bits } = readLabWav(buffer);
  return { seconds, sample_rate, channels, bits };
}

export function readLabWav(buffer: ArrayBuffer) {
  if (buffer.byteLength > MAX_AUDIO_BYTES) throw new Error('Choose a WAV smaller than 1 MB and no longer than 30 seconds.');
  if (buffer.byteLength < 44) throw new Error('This file is too short to contain a PCM WAV recording.');
  const view = new DataView(buffer);
  if (ascii(view, 0, 4) !== 'RIFF' || ascii(view, 8, 4) !== 'WAVE')
    throw new Error('Choose an uncompressed WAV file, not MP3, WebM or a renamed file.');
  const declaredEnd = view.getUint32(4, true) + 8;
  if (declaredEnd !== buffer.byteLength) throw new Error('The WAV length is inconsistent or the file is incomplete.');
  let format: { codec: number; channels: number; rate: number; byteRate: number; align: number; bits: number } | null = null;
  let bytes: number | null = null;
  let dataStart = 0;
  let offset = 12;
  for (; offset + 8 <= declaredEnd;) {
    const tag = ascii(view, offset, 4);
    const size = view.getUint32(offset + 4, true);
    const start = offset + 8;
    if (start + size > declaredEnd) throw new Error('The WAV contains an incomplete audio chunk.');
    if (tag === 'fmt ') {
      if (format || size < 16) throw new Error('The WAV has an invalid format header.');
      format = {
        codec: view.getUint16(start, true), channels: view.getUint16(start + 2, true),
        rate: view.getUint32(start + 4, true), byteRate: view.getUint32(start + 8, true),
        align: view.getUint16(start + 12, true), bits: view.getUint16(start + 14, true),
      };
    }
    if (tag === 'data') {
      if (!format) throw new Error('The WAV format header must appear before its audio data.');
      if (bytes !== null) throw new Error('Choose a WAV with one audio data chunk.');
      bytes = size;
      dataStart = start;
    }
    offset = start + size + (size % 2);
  }
  if (offset !== declaredEnd) throw new Error('The WAV contains an incomplete chunk header.');
  if (!format || bytes === null || bytes === 0 || bytes % 2 !== 0)
    throw new Error('The WAV must contain complete PCM samples.');
  if (format.codec !== 1 || format.channels !== 1 || format.rate !== SAMPLE_RATE || format.bits !== 16 || format.align !== 2 || format.byteRate !== SAMPLE_RATE * 2)
    throw new Error('Use mono, 16 kHz, 16-bit PCM WAV. Stereo or compressed WAV is not supported for screening.');
  const seconds = bytes / (SAMPLE_RATE * 2);
  if (seconds > MAX_AUDIO_SECONDS) throw new Error('Trim the recording to at most 30 seconds.');
  return { seconds, sample_rate: SAMPLE_RATE, channels: 1, bits: 16, dataStart, samples: bytes / 2 };
}

export function diagnosticWav(kind: DiagnosticFixture): ArrayBuffer {
  const samples = SAMPLE_RATE * 5;
  const buffer = new ArrayBuffer(44 + samples * 2);
  const view = new DataView(buffer);
  const write = (offset: number, text: string) => [...text].forEach((char, index) => view.setUint8(offset + index, char.charCodeAt(0)));
  write(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true); write(8, 'WAVE');
  write(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, SAMPLE_RATE, true);
  view.setUint32(28, SAMPLE_RATE * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  write(36, 'data'); view.setUint32(40, samples * 2, true);
  for (let index = 0; index < samples; index++) {
    const tone = Math.sin(2 * Math.PI * 180 * index / SAMPLE_RATE);
    const sample = kind === 'silence' ? 0 : kind === 'tone' ? Math.round(tone * 5_000) : tone >= 0 ? 32_767 : -32_768;
    view.setInt16(44 + index * 2, sample, true);
  }
  return buffer;
}

export async function getAudioLabStatus() {
  const status = await request<AudioLabStatus>('/audio-lab/status');
  if (status.provider_calls !== 0 || status.persisted !== false || typeof status.enabled !== 'boolean' || !['monitor', 'enforce', 'off'].includes(status.mode) || !status.model || typeof status.model.ready !== 'boolean')
    throw new Error('The service did not return the expected local-only screening status.');
  return status;
}

function validResult(value: AudioScreenResult | undefined) {
  if (!value || !['allow', 'suspicious', 'unknown'].includes(value.verdict) || value.experimental !== true || value.score_calibrated !== false || !value.model || !value.diagnostics || !Array.isArray(value.reasons)) return false;
  if (![value.compute_ms, value.audio_window_ms, value.analyzed_ms, value.partial_window_ms, value.windows_analyzed].every((number) => Number.isFinite(number) && number >= 0)) return false;
  if (value.analyzed_ms > value.audio_window_ms || value.audio_window_ms > 30_000) return false;
  if (value.score !== null && (!Number.isFinite(value.score) || value.score < 0 || value.score > 1 || value.model.kind !== 'onnx_classifier' || !value.model.ready)) return false;
  if (value.verdict !== 'unknown' && value.score === null) return false;
  return ['rms_dbfs', 'peak', 'clipping_ratio', 'silence_ratio', 'zero_crossing_rate', 'voiced_frames'].every((key) => Number.isFinite(value.diagnostics[key as keyof AudioScreenResult['diagnostics']]));
}

export async function analyzeAudio(file: File, consent: boolean): Promise<AudioLabResponse> {
  if (!consent) throw new Error('Confirm that you have permission to process this recording locally.');
  if (file.size > MAX_AUDIO_BYTES) throw new Error('Choose a WAV smaller than 1 MB and no longer than 30 seconds.');
  inspectScreeningWav(await file.arrayBuffer());
  const form = new FormData();
  form.append('audio', file);
  form.append('consent', 'true');
  const response = await request<AudioLabResponse>('/audio-lab/analyze', { method: 'POST', body: form }, undefined, 30_000);
  if (response.schema_version !== 1 || response.provider_calls !== 0 || response.persisted !== false || !validResult(response.result))
    throw new Error('The service did not return the expected local-only screening contract.');
  return response;
}

export function recordSharedLatency(sourceEnd: string, receiverStart: string, scenario: SharedRecordingObservation['scenario'], recordingId: string, duration: string): SharedRecordingObservation {
  if (!sourceEnd.trim() || !receiverStart.trim()) throw new Error('Enter both positions from the same recording.');
  const start = Number(sourceEnd), end = Number(receiverStart), length = Number(duration);
  if (!/^[a-zA-Z0-9_-]{1,48}$/.test(recordingId)) throw new Error('Use an anonymous recording ID with letters, numbers, hyphens or underscores.');
  if (!duration.trim() || !Number.isFinite(length) || length <= 0 || length > 86_400 || end > length)
    throw new Error('Enter the recording duration in seconds; both annotations must fit inside it.');
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < start || end > 86_400)
    throw new Error('Use finite seconds from one recording; received audio must start at or after the source phrase ends.');
  if (end - start > 120) throw new Error('A delay above 120 seconds should be recorded as a failure in the Test lab.');
  return {
    id: crypto.randomUUID(), observed_at: new Date().toISOString(),
    source_event_ms: Math.round(start * 1000), receiver_start_ms: Math.round(end * 1000),
    source_event: scenario === 'original_audio' ? 'source_marker_start' : 'source_phrase_end',
    delay_ms: Math.round((end - start) * 1000), boundary: 'manual_shared_recording', scenario,
    recording_id: recordingId, recording_duration_ms: Math.round(length * 1000),
  };
}

const rank = (values: number[], p: number) => values.length ? [...values].sort((a, b) => a - b)[Math.max(0, Math.ceil(values.length * p) - 1)] : null;
export function sharedLatencySummary(rows: SharedRecordingObservation[], scenario: SharedRecordingObservation['scenario']) {
  const values = rows.filter((row) => row.scenario === scenario && row.boundary === 'manual_shared_recording' && Number.isFinite(row.delay_ms) && row.delay_ms >= 0 && row.delay_ms <= 120_000).map((row) => row.delay_ms);
  return { count: values.length, p50_ms: rank(values, 0.5), p95_ms: rank(values, 0.95) };
}

/** Deliberately excludes file names, audio bytes, names, transcripts and session credentials. */
export function audioLabReport(screening: ScreeningObservation[], latency: SharedRecordingObservation[]) {
  return {
    schema_version: 1, generated_at: new Date().toISOString(), provider_calls: 0,
    scope: 'Local experimental screening and manually annotated shared-recording timing',
    limitations: 'Scores are uncalibrated. Diagnostic fixtures are not speech accuracy evidence. Timing is manually annotated, not automatic translation certification.',
    screening: screening.map((row) => ({
      id: row.id, observed_at: row.observed_at, expected_label: row.expected_label,
      diagnostic_fixture: row.diagnostic_fixture,
      verdict: row.result.verdict, score: row.result.score,
      model: { id: row.result.model.id, kind: row.result.model.kind, revision: row.result.model.revision, sha256: row.result.model.sha256, ready: row.result.model.ready, license: row.result.model.license, validated_on_indian_meeting_audio: row.result.model.validated_on_indian_meeting_audio },
      compute_ms: row.result.compute_ms, audio_window_ms: row.result.audio_window_ms,
      analyzed_ms: row.result.analyzed_ms, threshold: row.result.threshold,
      allow_threshold: row.result.allow_threshold, windows_analyzed: row.result.windows_analyzed,
      partial_window_ms: row.result.partial_window_ms, score_calibrated: row.result.score_calibrated,
      experimental: true,
      diagnostics: {
        rms_dbfs: row.result.diagnostics.rms_dbfs, peak: row.result.diagnostics.peak,
        clipping_ratio: row.result.diagnostics.clipping_ratio, silence_ratio: row.result.diagnostics.silence_ratio,
        zero_crossing_rate: row.result.diagnostics.zero_crossing_rate, pitch_hz: row.result.diagnostics.pitch_hz,
        jitter_percent: row.result.diagnostics.jitter_percent, shimmer_percent: row.result.diagnostics.shimmer_percent,
        voiced_frames: row.result.diagnostics.voiced_frames,
        variation_method: row.result.diagnostics.variation_method,
      },
    })),
    latency: latency.map((row) => ({
      id: row.id, observed_at: row.observed_at, source_event_ms: row.source_event_ms,
      source_event: row.source_event,
      receiver_start_ms: row.receiver_start_ms, delay_ms: row.delay_ms,
      boundary: row.boundary, scenario: row.scenario,
      recording_id: row.recording_id, recording_duration_ms: row.recording_duration_ms,
    })),
    latency_summary: {
      original_audio: sharedLatencySummary(latency, 'original_audio'),
      standard_translation: sharedLatencySummary(latency, 'standard_translation'),
    },
  };
}
