import type {
  Health,
  Language,
  Membership,
  Room,
  Turn,
  VoiceMode,
  VoiceProfile,
  Metrics,
} from '../types/domain';
import { createDemoRoom, getDemoRoom, joinDemo } from './demo';
import { isLanguage } from '../types/domain';
export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) || '/api';
export const DEMO_ALLOWED = import.meta.env.VITE_DEMO_MODE === 'true';
let fallback = false;
export const isLocalDemo = () => fallback;
export async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
  timeoutMs = 12000,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
    if (!response.ok) {
      let message = `Request failed (${response.status}).`;
      try {
        const body = await response.json();
        message =
          typeof body.detail === 'string'
            ? body.detail
            : body.error?.message || body.message || message;
      } catch {
        /* response has no JSON */
      }
      throw new Error(message);
    }
    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError')
      throw new Error('The service took too long to respond. Please try again.');
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
export async function checkHealth(): Promise<Health> {
  try {
    const result = await request<Health>('/health');
    if (
      !['demo', 'live', 'transport'].includes(result.mode) ||
      !Array.isArray(result.providers) ||
      !Array.isArray(result.languages) ||
      result.languages.some(
        (language) =>
          !language ||
          !isLanguage(language.code) ||
          typeof language.name !== 'string' ||
          typeof language.native_name !== 'string',
      ) ||
      result.providers.some(
        (provider) =>
          !provider ||
          typeof provider.name !== 'string' ||
          typeof provider.status !== 'string' ||
          typeof provider.detail !== 'string',
      )
    )
      throw new Error('This endpoint is not an Artha Mesh workspace service.');
    fallback = false;
    return result;
  } catch {
    if (!DEMO_ALLOWED)
      throw new Error(
        'The workspace service is unavailable. Start the server, or explicitly enable VITE_DEMO_MODE for a local demonstration.',
      );
    fallback = true;
    return { status: 'local', mode: 'demo', providers: [], languages: [], version: '1.0.0' };
  }
}
export const createRoom = (title: string): Promise<Room> =>
  fallback
    ? Promise.resolve(createDemoRoom(title))
    : request('/rooms', { method: 'POST', body: JSON.stringify({ title }) });
export const getRoom = (code: string): Promise<Room> =>
  fallback ? Promise.resolve(getDemoRoom(code)) : request(`/rooms/${encodeURIComponent(code)}`);
export const joinRoom = (
  code: string,
  name: string,
  language: Language,
  voice_mode: VoiceMode,
  consent: boolean,
  profile?: string,
): Promise<Membership> =>
  fallback
    ? Promise.resolve(joinDemo(code, name, language, voice_mode))
    : request(
        `/rooms/${encodeURIComponent(code)}/join`,
        {
          method: 'POST',
          body: JSON.stringify({ name, language, voice_mode, consent, voice_profile_id: profile }),
        },
        undefined,
        35000,
      );
export const leaveRoom = (m: Membership) =>
  m.localDemo
    ? Promise.resolve({ ok: true })
    : request(
        `/rooms/${m.room.code}/leave`,
        { method: 'POST', body: JSON.stringify({ participant_id: m.participant.id }) },
        m.session_token,
        4000,
      );
export const updateParticipant = (m: Membership, patch: Record<string, unknown>) =>
  m.localDemo
    ? Promise.resolve({ ...m.participant, ...patch })
    : request(
        `/rooms/${m.room.code}/participants/me`,
        { method: 'PATCH', body: JSON.stringify(patch) },
        m.session_token,
      );
export const getTranscript = (m: Membership) =>
  request<{ turns: Turn[]; metrics: Metrics }>(
    `/rooms/${m.room.code}/transcript`,
    {},
    m.session_token,
  );
export const startServerDemo = (m: Membership) =>
  request(
    `/rooms/${m.room.code}/demo`,
    { method: 'POST', body: JSON.stringify({ scenario: 'everyday' }) },
    m.session_token,
  );
export const submitText = (m: Membership, text: string) =>
  request(
    `/rooms/${m.room.code}/text`,
    { method: 'POST', body: JSON.stringify({ text }) },
    m.session_token,
  );
export const confirmTurn = (m: Membership, id: string) =>
  request<{ confirmed_by: string[] }>(
    `/rooms/${m.room.code}/confirmations`,
    { method: 'POST', body: JSON.stringify({ utterance_id: id }) },
    m.session_token,
  );
export async function uploadVoice(blob: Blob, name: string, m: Membership): Promise<VoiceProfile> {
  if (m.localDemo)
    return { id: crypto.randomUUID(), name, created_at: new Date().toISOString(), mode: 'demo' };
  const form = new FormData();
  form.append('audio_file', blob, `voice.${blob.type.includes('wav') ? 'wav' : 'webm'}`);
  form.append('name', name);
  form.append('consent', 'true');
  form.append('owner_token', m.session_token);
  return request('/voice-profiles', { method: 'POST', body: form }, undefined, 55000);
}
export const deleteVoice = (id: string, m: Membership) =>
  m.localDemo
    ? Promise.resolve({ ok: true })
    : request(`/voice-profiles/${id}`, { method: 'DELETE' }, m.session_token);
export function websocketUrl(code: string): string {
  const base = new URL(API_BASE, window.location.origin);
  base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
  base.pathname = `${base.pathname.replace(/\/$/, '')}/rooms/${encodeURIComponent(code)}/events`;
  return base.toString();
}
