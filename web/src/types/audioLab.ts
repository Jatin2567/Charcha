export type ScreeningVerdict = 'allow' | 'suspicious' | 'unknown';
export type ExpectedAudioLabel = 'unlabelled' | 'human' | 'synthetic';
export type DiagnosticFixture = 'silence' | 'tone' | 'clipping';

export interface ScreeningModel {
  id: string;
  kind: 'signal_only' | 'onnx_classifier';
  revision: string | null;
  sha256: string | null;
  ready: boolean;
  license: string | null;
  validated_on_indian_meeting_audio: false;
}

export interface AudioScreenResult {
  verdict: ScreeningVerdict;
  score: number | null;
  model: ScreeningModel;
  compute_ms: number;
  audio_window_ms: number;
  analyzed_ms: number;
  windows_analyzed: number;
  partial_window_ms: number;
  score_calibrated: false;
  reasons: string[];
  diagnostics: {
    rms_dbfs: number;
    peak: number;
    clipping_ratio: number;
    silence_ratio: number;
    zero_crossing_rate: number;
    pitch_hz: number | null;
    jitter_percent: number | null;
    shimmer_percent: number | null;
    voiced_frames: number;
    variation_method: string;
  };
  experimental: true;
  threshold: number | null;
  allow_threshold: number | null;
}

export interface AudioLabStatus {
  enabled: boolean;
  mode: 'monitor' | 'enforce' | 'off';
  model: ScreeningModel;
  max_seconds: number;
  sample_rate: number;
  provider_calls: 0;
  persisted: false;
}

export interface AudioLabResponse {
  schema_version: 1;
  provider_calls: 0;
  persisted: false;
  result: AudioScreenResult;
}

export interface ScreeningObservation {
  id: string;
  observed_at: string;
  expected_label: ExpectedAudioLabel;
  diagnostic_fixture: DiagnosticFixture | null;
  result: AudioScreenResult;
}

export interface SharedRecordingObservation {
  id: string;
  observed_at: string;
  source_event_ms: number;
  source_event: 'source_marker_start' | 'source_phrase_end';
  receiver_start_ms: number;
  delay_ms: number;
  boundary: 'manual_shared_recording';
  scenario: 'original_audio' | 'standard_translation';
  recording_id: string;
  recording_duration_ms: number;
}
