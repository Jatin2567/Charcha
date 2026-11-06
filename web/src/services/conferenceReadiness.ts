import { API_BASE } from './api';
import { isLanguage } from '../types/domain';
import type { Language, Membership, Participant } from '../types/domain';

const RESOURCES = [
  'stt_seconds',
  'stt_connections',
  'mt_requests',
  'mt_characters',
  'tts_requests',
  'tts_characters',
] as const;
export interface ConferenceReadiness {
  schema_version: 1;
  room_code: string;
  mode: 'live' | 'transport' | 'demo';
  generated_at?: string;
  membership: {
    active: boolean;
    muted: boolean;
    language: Language;
    voice_mode: 'standard' | 'cloned';
  };
  media: { interpreter_connected: boolean; member_connected: boolean };
  audience: {
    other_participants: number;
    translation_target_languages: Language[];
    connected_translation_target_languages: Language[];
    same_language_listeners: number;
  };
  providers: { configured: boolean; missing: string[]; verification: 'not_checked' };
  provider_flow: {
    authorization?: 'operator' | 'host_budget';
    required: boolean;
    status: 'locked' | 'approved' | 'expired' | 'exhausted' | 'unavailable' | 'not_required';
    expires_at: string | null;
    remaining: Record<(typeof RESOURCES)[number], number | null>;
  };
  source: { recognizer_task_active: boolean };
  microphone: {
    can_unmute: boolean;
    may_start_new_source: boolean;
    reason_code: string;
    detail: string;
  };
}
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
const count = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0;
const publicText = (value: unknown): value is string =>
  typeof value === 'string' &&
  value.length <= 700 &&
  !/vach_[A-Za-z0-9_-]+|Bearer\s+\S+/i.test(value);

export class ConferenceRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code = 'conference_unavailable',
  ) {
    super(message);
    this.name = 'ConferenceRequestError';
  }
  get staleMembership() {
    return [401, 403, 404, 410].includes(this.status);
  }
}

export function conferenceReadiness(value: unknown, code: string): ConferenceReadiness | null {
  if (
    !record(value) ||
    value.schema_version !== 1 ||
    value.room_code !== code ||
    !['live', 'transport', 'demo'].includes(String(value.mode)) ||
    (value.generated_at !== undefined &&
      (typeof value.generated_at !== 'string' ||
        !Number.isFinite(Date.parse(value.generated_at)))) ||
    !record(value.membership) ||
    !record(value.media) ||
    !record(value.audience) ||
    !record(value.providers) ||
    !record(value.provider_flow) ||
    !record(value.source) ||
    !record(value.microphone)
  )
    return null;
  const { membership, media, audience, providers, provider_flow: flow, source, microphone } = value;
  if (
    typeof membership.active !== 'boolean' ||
    typeof membership.muted !== 'boolean' ||
    !isLanguage(membership.language) ||
    !['standard', 'cloned'].includes(String(membership.voice_mode)) ||
    typeof media.interpreter_connected !== 'boolean' ||
    typeof media.member_connected !== 'boolean' ||
    !count(audience.other_participants) ||
    !count(audience.same_language_listeners) ||
    !Array.isArray(audience.translation_target_languages) ||
    !audience.translation_target_languages.every(isLanguage) ||
    !Array.isArray(audience.connected_translation_target_languages) ||
    !audience.connected_translation_target_languages.every(isLanguage) ||
    typeof providers.configured !== 'boolean' ||
    !Array.isArray(providers.missing) ||
    !providers.missing.every(publicText) ||
    providers.verification !== 'not_checked' ||
    typeof flow.required !== 'boolean' ||
    !['locked', 'approved', 'expired', 'exhausted', 'unavailable', 'not_required'].includes(
      String(flow.status),
    ) ||
    !(
      flow.expires_at === null ||
      (typeof flow.expires_at === 'string' && Number.isFinite(Date.parse(flow.expires_at)))
    ) ||
    !record(flow.remaining) ||
    RESOURCES.some(
      (key) =>
        (flow.remaining as Record<string, unknown>)[key] !== null &&
        !count((flow.remaining as Record<string, unknown>)[key]),
    ) ||
    typeof source.recognizer_task_active !== 'boolean' ||
    typeof microphone.can_unmute !== 'boolean' ||
    typeof microphone.may_start_new_source !== 'boolean' ||
    typeof microphone.reason_code !== 'string' ||
    !/^[a-z0-9_]{1,100}$/.test(microphone.reason_code) ||
    !publicText(microphone.detail)
  )
    return null;
  return value as unknown as ConferenceReadiness;
}

async function conferenceRequest(
  path: string,
  m: Membership,
  options: RequestInit = {},
  signal?: AbortSignal,
): Promise<unknown> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) controller.abort();
  const timer = setTimeout(abort, 8000);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${m.session_token}` },
    });
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = record(body) ? body.detail : null;
      const code =
        record(detail) && typeof detail.code === 'string' && /^[a-z0-9_]{1,100}$/.test(detail.code)
          ? detail.code
          : 'conference_unavailable';
      const fallback = [401, 403, 404, 410].includes(response.status)
        ? 'Your room membership has ended. Rejoin the conversation to continue.'
        : 'The room could not confirm this change. Keep the microphone muted and retry.';
      const message = publicText(detail)
        ? detail
        : record(detail) && publicText(detail.message)
          ? detail.message
          : fallback;
      throw new ConferenceRequestError(message, response.status, code);
    }
    return body;
  } catch (error) {
    if (error instanceof ConferenceRequestError) throw error;
    if (signal?.aborted) throw error;
    throw new ConferenceRequestError(
      'The room service is unavailable. Check the connection and retry.',
      0,
    );
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}

export async function fetchConferenceReadiness(m: Membership, signal?: AbortSignal) {
  const value = await conferenceRequest(
    `/rooms/${encodeURIComponent(m.room.code)}/conference-readiness`,
    m,
    {},
    signal,
  );
  const report = conferenceReadiness(value, m.room.code);
  if (!report)
    throw new ConferenceRequestError(
      'Room readiness is incomplete. Keep the microphone muted and refresh.',
      0,
    );
  return report;
}

export async function setConferenceMuted(m: Membership, muted: boolean): Promise<Participant> {
  const value = await conferenceRequest(
    `/rooms/${encodeURIComponent(m.room.code)}/participants/me`,
    m,
    { method: 'PATCH', body: JSON.stringify({ muted }) },
  );
  if (!record(value) || value.id !== m.participant.id || value.muted !== muted)
    throw new ConferenceRequestError(
      'The microphone state could not be confirmed. Reconnect the room.',
      0,
    );
  return value as unknown as Participant;
}
