import type { Language } from './domain';

export type SampleStatus = 'complete' | 'error' | 'cancelled';
export type MeasurementKind = 'server_first_pcm' | 'source_forwarded' | 'simulated';
export interface PerformanceSample {
  id: string;
  utterance_id: string;
  source_language: Language;
  target_language: Language;
  input_kind: 'audio' | 'text';
  voice_mode: 'standard' | 'cloned';
  status: SampleStatus;
  measurement: MeasurementKind;
  queue_ms: number | null;
  stt_ms: number | null;
  mt_ms: number | null;
  tts_first_pcm_ms: number | null;
  total_ms: number | null;
  created_at: string;
  error_stage?: string | null;
}
export interface DirectionSummary {
  source_language: Language;
  target_language: Language;
  sample_count: number;
  success_count: number;
  error_count: number;
  cancelled_count: number;
  live_sample_count: number;
  p50_ms: number | null;
  p95_ms: number | null;
}
export interface PerformanceSummary {
  sample_count: number;
  success_count: number;
  error_count: number;
  cancelled_count: number;
  live_sample_count: number;
  forwarded_count: number;
  simulated_count: number;
  p50_ms: number | null;
  p95_ms: number | null;
  by_direction: DirectionSummary[];
}
export interface PerformanceReport {
  room_code: string;
  mode: 'demo' | 'live' | 'transport';
  generated_at: string;
  measurement: {
    boundary: 'server_first_pcm';
    stt: 'processing_to_transcript';
    total: 'queue_to_first_pcm_plus_stt';
    receiver_playback_measured: false;
    retention_limit: number;
  };
  summary: PerformanceSummary;
  samples: PerformanceSample[];
}
export interface ReadinessRequirement {
  key: string;
  label: string;
  configured: boolean;
  required: boolean;
  group: string;
  detail: string;
}
export interface DeploymentCheck {
  key: string;
  label: string;
  status: 'manual';
  detail: string;
}
export interface ReadinessReport {
  mode: 'demo' | 'live' | 'transport';
  generated_at: string;
  requirements: ReadinessRequirement[];
  provider_verification: 'not_checked';
  deployment_checks: DeploymentCheck[];
}
export interface PerformanceFilter {
  direction: string;
  input: 'all' | 'audio' | 'text';
  voice: 'all' | 'standard' | 'cloned';
  status: 'all' | SampleStatus;
}
