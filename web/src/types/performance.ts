import type { Language } from './domain';
import type { TransportMetrics } from '../services/transportMetrics';

export interface MeetingReportEntry {
  report_id: string;
  room_code: string;
  title: string;
  started_at: string;
  saved_at: string | null;
  ended_at: string | null;
  status: 'active' | 'completed' | 'interrupted';
}

export type SampleStatus = 'complete' | 'error' | 'cancelled';
export type MeasurementKind = 'server_first_pcm' | 'source_forwarded' | 'simulated';
export interface PersistenceStatus {
  state: 'saved' | 'pending' | 'retrying' | 'unavailable';
  last_saved_at: string | null;
  pending: number;
  error: string | null;
}
export interface TurnLatencySample {
  marker_id: string;
  utterance_id: string;
  listener_id: string;
  source_language: Language;
  target_language: Language;
  status: 'detected' | 'ambiguous' | 'muted' | 'blocked' | 'timeout' | 'source_unavailable' | 'unreported';
  source_end_status: string;
  latency_ms: number | null;
  uncertainty_ms: number | null;
  source_end_to_first_pcm_ms: number | null;
  physical_playback_measured: false;
  client_reported: true;
  created_at: string;
}
export interface TurnLatencyReport {
  measurement: 'server_ingress_energy_end_to_browser_decoded_onset_estimate';
  physical_playback_measured: false;
  samples: TurnLatencySample[];
}
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
  queue_depth?: number | null;
  preparation_ms?: number | null;
  output_wait_ms?: number | null;
  stt_ms: number | null;
  source_end_status?: string | null;
  source_end_to_transcript_ms?: number | null;
  source_end_to_first_pcm_ms?: number | null;
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
  report_id?: string;
  title?: string;
  started_at?: string;
  saved_at?: string | null;
  ended_at?: string | null;
  status?: MeetingReportEntry['status'];
  view?: 'live' | 'saved';
  participant_ids?: string[];
  connection?: TransportMetrics | null;
  receiver_audio?: unknown;
  turn_latency?: TurnLatencyReport;
  persistence?: PersistenceStatus;
  participant_id?: string;
  room_code: string;
  mode: 'demo' | 'live' | 'transport';
  generated_at: string;
  measurement: {
    boundary: 'server_first_pcm';
    stt: 'processing_to_transcript';
    total: 'queue_to_first_pcm_plus_stt';
    receiver_playback_measured: false;
    retention_limit: number;
    total_coverage?: string;
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
