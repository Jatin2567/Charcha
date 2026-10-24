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
}
