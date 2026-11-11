import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  changeResource,
  preparationLabel,
  resourcePayload,
  reviewerAccessIsCurrent,
  reviewerAccess,
  reviewerRequestState,
  requestReviewerAccess,
  reviewerRequests,
  decideReviewerRequest,
  type ReviewerAccess,
  type ResourceForm,
} from './reviewer';

afterEach(() => vi.unstubAllGlobals());

const form: ResourceForm = {
  gnani_source: 'own',
  evon_source: 'own',
  gnani_api_key: ' speech-test ',
  evon_base_url: 'https://reviewer.modal.run/v1',
  evon_model: 'review-model',
  evon_api_key: 'model-test',
  evon_modal_key: 'proxy-test',
  evon_modal_secret: 'proxy-secret-test',
};
describe('reviewer resource boundaries', () => {
  it('ends local reviewer permission at expiry even before the next server poll', () => {
    const access = {
      reviewer: true,
      can_host: true,
      reviewer_shared_allowed: true,
      expires_at: 100,
    };
    expect(reviewerAccessIsCurrent(access, 99999)).toBe(true);
    expect(reviewerAccessIsCurrent(access, 100000)).toBe(false);
    expect(reviewerAccessIsCurrent({ ...access, can_host: false }, 90000)).toBe(false);
    expect(reviewerAccessIsCurrent(null)).toBe(false);
  });
  it('discards credentials typed for a previous endpoint before changing destination', () => {
    const changed = changeResource(form, 'evon_base_url', 'https://another.modal.run/v1');
    expect(changed.evon_api_key).toBe('');
    expect(changed.evon_modal_key).toBe('');
    expect(changed.evon_modal_secret).toBe('');
    expect(changed.gnani_api_key).toBe(form.gnani_api_key);
  });
  it('does not restore hidden credentials after switching away from an own service', () => {
    const shared = changeResource(form, 'gnani_source', 'shared');
    expect(changeResource(shared, 'gnani_source', 'own').gnani_api_key).toBe('');
    expect(changeResource(form, 'evon_source', 'shared').evon_modal_secret).toBe('');
  });
  it('drops all custom credentials and destinations when shared resources are selected', () => {
    expect(resourcePayload({ ...form, gnani_source: 'shared', evon_source: 'shared' })).toEqual({
      gnani_source: 'shared',
      evon_source: 'shared',
      resource_consent: true,
    });
  });
  it('sends only the selected service credentials for mixed sources', () => {
    const payload = resourcePayload({ ...form, gnani_source: 'shared' });
    expect(payload).not.toHaveProperty('gnani_api_key');
    expect(payload.evon_api_key).toBe('model-test');
    expect(payload).not.toHaveProperty('host_email');
  });
  it('omits empty write-only fields so an unchanged stored secret is not erased', () => {
    expect(
      resourcePayload({
        ...form,
        gnani_api_key: '',
        evon_api_key: '',
        evon_modal_key: '',
        evon_modal_secret: '',
      }),
    ).toEqual({
      gnani_source: 'own',
      evon_source: 'own',
      resource_consent: true,
      evon_base_url: form.evon_base_url,
      evon_model: form.evon_model,
    });
  });
  it('does not present external, unmeasured or unavailable engines as ready', () => {
    expect(preparationLabel(null)).toContain('not been measured');
    expect(preparationLabel({ available: true, can_prepare: true, state: 'external' })).toContain(
      'not been measured',
    );
    expect(
      preparationLabel({
        available: false,
        can_prepare: false,
        state: 'ready',
        detail: 'Access expired',
      }),
    ).toBe('Access expired');
  });
});

describe('verified-domain and administrator-review access', () => {
  const unavailable: ReviewerAccess = {
    reviewer: false,
    can_host: false,
    reviewer_shared_allowed: false,
    auto_domains: ['gnani.ai'],
    access_source: null,
  };
  function state(status: 'pending' | 'approved' | 'denied' | 'revoked' | 'expired') {
    return {
      ...unavailable,
      request: {
        id: 'request-1',
        email: 'reviewer@example.com',
        status,
        created_at: 1,
      },
    };
  }
  it('does not turn domain metadata or a pending request into local meeting permission', () => {
    expect(reviewerAccessIsCurrent({ ...state('pending'), access_source: 'domain' })).toBe(false);
    expect(reviewerRequestState(state('pending')).canRequest).toBe(false);
    expect(reviewerRequestState(unavailable).canRequest).toBe(true);
  });
  it.each(['denied', 'revoked'] as const)(
    'keeps %s accounts blocked rather than offering invitation bypass',
    (status) => {
      expect(reviewerRequestState(state(status))).toMatchObject({
        canRequest: false,
        canRedeem: false,
      });
      expect(reviewerAccessIsCurrent(state(status))).toBe(false);
    },
  );
  it('permits an explicit renewal request after expiry without presenting access as active', () => {
    const expired = { ...state('expired'), reviewer: true, can_host: true, expires_at: 100 };
    expect(reviewerAccessIsCurrent(expired, 100001)).toBe(false);
    expect(reviewerRequestState(expired).canRequest).toBe(true);
  });
  it('requests access using only the authenticated session, never a submitted email or role', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(state('pending'))));
    vi.stubGlobal('fetch', fetcher);
    await requestReviewerAccess();
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe('/api/reviewer/access/request');
    expect(init).toMatchObject({ method: 'POST', credentials: 'same-origin' });
    expect(init.body).toBeUndefined();
    expect(init.headers['X-Charcha-Request']).toBe('1');
  });
  it('reads access and approval queues without posting to provider or preparation routes', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{}'));
    vi.stubGlobal('fetch', fetcher);
    await reviewerAccess();
    fetcher.mockResolvedValue(new Response('{"requests":[]}'));
    await reviewerRequests();
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      '/api/reviewer/access',
      '/api/admin/reviewer-requests',
    ]);
    expect(fetcher.mock.calls.every(([, init]) => !init.method || init.method === 'GET')).toBe(
      true,
    );
  });
  it('sends an explicit admin decision and resource choice for the encoded request ID', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{}'));
    vi.stubGlobal('fetch', fetcher);
    await decideReviewerRequest('request/with space', 'approve', 24, false);
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe('/api/admin/reviewer-requests/request%2Fwith%20space/decision');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      decision: 'approve',
      expires_in_hours: 24,
      share_resources: false,
    });
  });
});
