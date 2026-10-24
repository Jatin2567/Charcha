export type UsageKey =
  | 'stt_seconds'
  | 'stt_connections'
  | 'mt_requests'
  | 'mt_characters'
  | 'tts_requests'
  | 'tts_characters'
  | 'voice_enrollments';

export type UsageStatus = 'available' | 'warning' | 'exhausted' | 'unknown';
export interface UsageResource {
  key: UsageKey;
  label: string;
  unit: 'seconds' | 'connections' | 'requests' | 'characters' | 'enrollments';
  used: number | null;
  limit: number;
  remaining: number | null;
  utilization_percent: number | null;
  status: UsageStatus;
}
export type FlowResources = Record<UsageKey, number>;
export type BalanceUnit = 'INR' | 'programme_credits';
export interface FlowMetrics {
  tts_first_pcm_ms?: number;
  tts_total_ms?: number;
  stt_final_ms?: number;
  tts_audio_seconds?: number;
  reference_seconds?: number;
  error_stage?: 'none' | 'tts' | 'stt' | 'enrollment' | 'configuration' | 'approval' | 'cancelled';
}
export interface ProviderFlow {
  id: string;
  purpose: 'gnani_speech_check' | 'voice_clone_check' | 'live_interpretation';
  status: 'approved' | 'closed' | 'expired' | 'exhausted';
  started_at: string;
  expires_at: string;
  closed_at: string | null;
  budgets: FlowResources;
  used: FlowResources;
  balance_unit: BalanceUnit | null;
  balance_delta: number | null;
  credits_used: number | null;
  credits_source: 'unknown' | 'manual_dashboard_delta';
  before_balance: number | null;
  before_observed_at: string | null;
  after_balance: number | null;
  after_observed_at: string | null;
  metrics: FlowMetrics;
}
export interface FlowApproval {
  required: boolean;
  status: 'locked' | 'approved' | 'unavailable' | 'demo';
  active_flow_id: string | null;
  expires_at: string | null;
  detail: string;
}
export interface ProgrammePricing {
  currency: 'INR';
  source: 'user_provided_pricing_table';
  reference_url: 'https://app.gnani.ai/voice/pricing';
  stt_per_hour: number | null;
  tts_per_10000_characters: number | null;
  voice_enrollment: null;
  rounding: 'unconfirmed';
}
export interface ProgrammeUsage {
  source: 'not_connected' | 'manual_dashboard' | 'user_reported';
  unit: BalanceUnit | null;
  balance: number | null;
  observed_at: string | null;
  automatic_sync: false;
  detail: string;
  quoted_rate: {
    amount: number;
    currency: 'INR';
    unit: 'request';
    source: 'user_reported';
    scope: 'unconfirmed';
  } | null;
  pricing: ProgrammePricing | null;
  flows: ProviderFlow[];
}
export interface UsageReport {
  mode: 'demo' | 'live';
  period: { date: string; reset_at: string };
  enforcement: {
    enabled: true;
    persistent: boolean;
    status: 'ready' | 'unavailable' | 'demo';
    detail: string;
  };
  resources: UsageResource[];
  billing: { balance_available: false; detail: string };
  approval: FlowApproval;
  programme: ProgrammeUsage;
}
