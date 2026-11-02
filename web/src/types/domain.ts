export type Language = 'hi' | 'ta' | 'bn' | 'en' | 'te' | 'kn' | 'ml' | 'mr' | 'gu' | 'pa';
export type VoiceMode = 'standard' | 'cloned';
export interface Participant {
  id: string;
  name: string;
  language: Language;
  voice_mode: VoiceMode;
  muted: boolean;
  is_agent: boolean;
  is_demo: boolean;
  joined_at: string;
}
export interface Room {
  id: string;
  code: string;
  title: string;
  created_at: string;
  mode: 'demo' | 'live' | 'transport';
  participants: Participant[];
}
export interface Turn {
  id: string;
  speaker_id: string;
  speaker_name: string;
  source_language: Language;
  text: string;
  created_at: string;
  translations: Partial<Record<Language, string>>;
  confirmed_by: string[];
  status: 'processing' | 'complete' | 'error';
}
export interface Metrics {
  turns: number;
  stt_ms: number;
  mt_ms: number;
  tts_ms: number;
  total_ms: number;
  p50_ms: number;
  p95_ms: number;
  measurement: 'server_pipeline';
}
export interface Health {
  status: string;
  mode: 'demo' | 'live' | 'transport';
  providers: { name: string; status: string; detail: string }[];
  languages: { code: Language; name: string; native_name: string }[];
  version: string;
}
export interface Membership {
  room: Room;
  participant: Participant;
  session_token: string;
  livekit: null | { url: string; token: string; agent_identity: string };
  localDemo?: boolean;
}
export interface VoiceProfile {
  id: string;
  name: string;
  created_at: string;
  mode: 'demo' | 'live';
}
export interface AppEvent {
  id: string;
  type: string;
  timestamp: string;
  payload: Record<string, unknown>;
}
export interface Preferences {
  name: string;
  language: Language;
  inputDevice: string;
  outputDevice: string;
  autoCaptions: boolean;
  largeCaptions: boolean;
  micEnabled: boolean;
  highContrast: boolean;
}
export interface Recap {
  id: string;
  room: Room;
  participant: Participant;
  turns: Turn[];
  metrics: Metrics | null;
  ended_at: string;
  localDemo: boolean;
  cleanup_warning?: string;
}
export const LANGUAGES: { code: Language; name: string; native: string; short: string }[] = [
  { code: 'hi', name: 'Hindi', native: 'हिन्दी', short: 'HI' },
  { code: 'ta', name: 'Tamil', native: 'தமிழ்', short: 'TA' },
  { code: 'bn', name: 'Bengali', native: 'বাংলা', short: 'BN' },
  { code: 'en', name: 'English', native: 'English', short: 'EN' },
  { code: 'te', name: 'Telugu', native: 'తెలుగు', short: 'TE' },
  { code: 'kn', name: 'Kannada', native: 'ಕನ್ನಡ', short: 'KN' },
  { code: 'ml', name: 'Malayalam', native: 'മലയാളം', short: 'ML' },
  { code: 'mr', name: 'Marathi', native: 'मराठी', short: 'MR' },
  { code: 'gu', name: 'Gujarati', native: 'ગુજરાતી', short: 'GU' },
  { code: 'pa', name: 'Punjabi', native: 'ਪੰਜਾਬੀ', short: 'PA' },
];
export const isLanguage = (value: unknown): value is Language =>
  typeof value === 'string' && LANGUAGES.some((entry) => entry.code === value);
export const SCRIPTED_LANGUAGE_CODES: readonly Language[] = ['hi', 'ta', 'bn', 'en'];
export const isScriptedLanguage = (code: Language) => SCRIPTED_LANGUAGE_CODES.includes(code);
export const SCRIPTED_LANGUAGES = LANGUAGES.filter((entry) => isScriptedLanguage(entry.code));
export const languageName = (code: Language) =>
  LANGUAGES.find((l) => l.code === code)?.name ?? code;
