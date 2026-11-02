import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ConferenceRequestError,
  conferenceReadiness,
  fetchConferenceReadiness,
  setConferenceMuted,
} from './conferenceReadiness';
import { ConferenceStatus } from '../components/ConferenceStatus';
import type { Membership } from '../types/domain';
import { approvalLabel, approvalSeconds, conferenceTitle, timeLeft } from './conferencePresentation';
import { ConferenceAllowance } from '../components/ConferenceAllowance';

const membership = {
  room: { code: 'room-1', mode: 'live' },
  participant: { id: 'self' },
  session_token: 'test-session',
} as Membership;
const fixture = () => ({
  schema_version: 1,
  room_code: 'room-1',
  mode: 'live',
  generated_at: '2026-10-30T14:00:00Z',
  membership: { active: true, muted: true, language: 'hi', voice_mode: 'standard' },
  media: { interpreter_connected: true, member_connected: true },
  audience: {
    other_participants: 1,
    translation_target_languages: ['ta'],
    connected_translation_target_languages: ['ta'],
    same_language_listeners: 0,
  },
  providers: { configured: true, missing: [], verification: 'not_checked' },
  provider_flow: {
    required: true,
    status: 'locked',
    expires_at: null,
    remaining: {
      stt_seconds: null,
      stt_connections: null,
      mt_requests: null,
      mt_characters: null,
      tts_requests: null,
      tts_characters: null,
    },
  },
  source: { recognizer_task_active: false },
  microphone: {
    can_unmute: false,
    may_start_new_source: false,
    reason_code: 'provider_flow_locked',
    detail: 'Ask the operator to approve a bounded interpretation flow.',
  },
});
afterEach(() => vi.unstubAllGlobals());

describe('authenticated read-only conference readiness', () => {
  it('validates unknown budget units without turning them into zero or model verification', () => {
    const value = conferenceReadiness(fixture(), 'room-1')!;
    expect(value).not.toBeNull();
    expect(value.provider_flow.remaining.stt_connections).toBeNull();
    expect(value.providers.verification).toBe('not_checked');
    expect(conferenceReadiness(fixture(), 'another-room')).toBeNull();
    expect(
      conferenceReadiness(
        { ...fixture(), providers: { configured: true, missing: [], verification: 'passed' } },
        'room-1',
      ),
    ).toBeNull();
    expect(
      conferenceReadiness(
        { ...fixture(), microphone: { ...fixture().microphone, detail: 'Bearer PRIVATE-TOKEN' } },
        'room-1',
      ),
    ).toBeNull();
  });

  it('uses only the authenticated room GET and does not request inference or approval', async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify(fixture()), { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    await fetchConferenceReadiness(membership);
    expect(fetch).toHaveBeenCalledOnce();
    const [path, options] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe('/api/rooms/room-1/conference-readiness');
    expect(options.method).toBeUndefined();
    expect(options.headers).toMatchObject({ Authorization: 'Bearer test-session' });
    expect(options.body).toBeUndefined();
  });

  it('keeps structured guard errors and identifies expired or missing memberships', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              detail: {
                code: 'provider_flow_expired',
                message: 'The approved flow expired. Keep the microphone muted.',
              },
            }),
            { status: 409 },
          ),
      ),
    );
    await expect(setConferenceMuted(membership, false)).rejects.toMatchObject({
      status: 409,
      code: 'provider_flow_expired',
      staleMembership: false,
    });
    for (const status of [401, 403, 404, 410])
      expect(new ConferenceRequestError('Rejoin', status).staleMembership).toBe(true);
    expect(new ConferenceRequestError('Offline', 0).staleMembership).toBe(false);
  });

  it('offers explicit speaker unlock and rejoin paths without autoplay or permission side effects', () => {
    const props = {
      report: conferenceReadiness(fixture(), 'room-1'),
      error: '',
      stale: false,
      mediaReady: true,
      muted: true,
      playback: { status: 'blocked' as const, error: '' },
      unlocking: false,
      onUnlock: () => {},
      onRetry: () => {},
      onRejoin: () => {},
    };
    const locked = renderToStaticMarkup(createElement(ConferenceStatus, props));
    expect(locked).toContain('waiting for operator approval');
    expect(locked).toContain('Enable speaker');
    const stale = renderToStaticMarkup(createElement(ConferenceStatus, { ...props, stale: true }));
    expect(stale).toContain('Rejoin conversation');
    const active = renderToStaticMarkup(
      createElement(ConferenceStatus, { ...props, muted: false }),
    );
    expect(active).toContain('Your microphone is on');
    expect(active).toContain('You can always mute');
  });
  it('separates missing configuration, expired approval and exhausted allowance', () => {
    const report = conferenceReadiness(fixture(), 'room-1')!;
    report.microphone.reason_code = 'provider_configuration_missing';
    expect(conferenceTitle(report, true, false, true, null)).toContain('needs configuration');
    report.microphone.reason_code = 'provider_flow_expired';
    report.provider_flow.status = 'expired';
    expect(conferenceTitle(report, true, false, true, 0)).toContain('has expired');
    report.provider_flow.status = 'exhausted';
    expect(conferenceTitle(report, true, false, true, 0)).toContain('allowance is used up');
    expect(conferenceTitle(report, false, false, true, 0)).toBe('Your microphone is on');
  });
  it('counts down using server time and elapsed time, including a stale approved snapshot', () => {
    const report = conferenceReadiness(fixture(), 'room-1')!;
    report.provider_flow.status = 'approved';
    report.provider_flow.expires_at = '2026-10-30T14:01:30Z';
    expect(approvalSeconds(report, 10)).toBe(80);
    expect(timeLeft(80)).toBe('About 1:20 remaining');
    expect(approvalSeconds(report, 95)).toBe(0);
    expect(conferenceTitle(report, true, false, true, 0)).toContain('has expired');
    expect(approvalSeconds({ ...report, generated_at: undefined })).toBeNull();
    expect(timeLeft(null)).toContain('unavailable');
    expect(approvalLabel('approved', 0)).toBe('expired');
    expect(approvalLabel('approved', 30)).toBe('approved');
    expect(approvalLabel('not_required', null)).toBe('not required');
  });
  it('shows unknown vs zero units without asserting model access or granting a flow', () => {
    const report = conferenceReadiness(fixture(), 'room-1')!;
    report.provider_flow.remaining.mt_requests = 0;
    const html = renderToStaticMarkup(
      createElement(ConferenceAllowance, { report, seconds: null }),
    );
    expect(html).toContain('Not checked');
    expect(html).toContain('Not available');
    expect(html).toContain('0 requests');
    expect(html).toContain('not a rupee charge');
    expect(html).toContain('No flow is approved or renewed from this page');
    expect(html).not.toContain('<button');
    expect(conferenceReadiness({ ...fixture(), generated_at: 'bad-date' }, 'room-1')).toBeNull();
  });
});
