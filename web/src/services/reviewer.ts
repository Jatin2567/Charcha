import { request } from './api';

export type ReviewerAccess = {
  reviewer: boolean;
  can_host: boolean;
  reviewer_shared_allowed: boolean;
  expires_at?: number | null;
  auto_domains?: string[];
  access_source?: 'domain' | 'approval' | 'invitation' | null;
  request?: ReviewerAccessStatus | null;
};
export type ReviewerAccessRequest = {
  id: string;
  email: string;
  status: 'pending' | 'approved' | 'denied' | 'revoked' | 'expired';
  created_at: number;
  reviewed_at?: number | null;
  expires_at?: number | null;
  share_resources?: boolean;
  source?: 'domain' | 'request';
};
export type ReviewerAccessStatus = Omit<ReviewerAccessRequest, 'id' | 'created_at'> & {
  id: string | null;
  created_at: number | null;
};

export function reviewerRequestState(access: ReviewerAccess) {
  const status = access.request?.status;
  if (status === 'pending')
    return {
      title: 'Awaiting administrator approval',
      detail:
        'Your verified email is in the approval queue. This page checks for a decision automatically.',
      canRequest: false,
      canRedeem: true,
    };
  if (status === 'denied' || status === 'revoked')
    return {
      title: status === 'denied' ? 'Reviewer request declined' : 'Reviewer access revoked',
      detail:
        'The administrator must approve access before you can host reviewer meetings. Signing in again does not override this decision.',
      canRequest: false,
      canRedeem: false,
    };
  if (status === 'expired' || status === 'approved')
    return {
      title: 'Reviewer access expired',
      detail:
        'Request access again. Eligible verified Gnani-domain accounts can renew automatically; other accounts need administrator approval.',
      canRequest: true,
      canRedeem: true,
    };
  return {
    title: 'Request reviewer access',
    detail:
      'Use your signed-in, verified email to request permission to create meetings and admit participants. The administrator reviews other email domains.',
    canRequest: true,
    canRedeem: true,
  };
}
export function reviewerAccessIsCurrent(access: ReviewerAccess | null, now = Date.now()) {
  return (
    !!access?.can_host &&
    !(access.reviewer && access.expires_at != null && access.expires_at * 1000 <= now)
  );
}
export type ResourceSource = 'shared' | 'own';
export type ReviewerProfile = {
  gnani_source: ResourceSource;
  evon_source: ResourceSource;
  evon_base_url: string;
  evon_model: string;
  gnani_key_set: boolean;
  evon_key_set: boolean;
  modal_proxy_set: boolean;
};
export type ReviewerWorkspace = {
  access: ReviewerAccess;
  profile: ReviewerProfile | null;
  configured: boolean;
  missing: string[];
};
export type ResourceForm = {
  gnani_source: ResourceSource;
  evon_source: ResourceSource;
  gnani_api_key: string;
  evon_base_url: string;
  evon_model: string;
  evon_api_key: string;
  evon_modal_key: string;
  evon_modal_secret: string;
};

// Credentials typed for one destination must not follow an endpoint change.
export function changeResource<K extends keyof ResourceForm>(
  form: ResourceForm,
  key: K,
  value: ResourceForm[K],
): ResourceForm {
  const next = { ...form, [key]: value };
  if (key === 'gnani_source' && value !== form.gnani_source) next.gnani_api_key = '';
  if (
    (key === 'evon_source' && value !== form.evon_source) ||
    (key === 'evon_base_url' && value !== form.evon_base_url)
  ) {
    next.evon_api_key = '';
    next.evon_modal_key = '';
    next.evon_modal_secret = '';
  }
  return next;
}

// Explicit allowlist: never send old custom credentials when shared resources
// are selected, and don't erase an unchanged secret with an empty form field.
export function resourcePayload(form: ResourceForm) {
  const body: Record<string, string | boolean> = {
    gnani_source: form.gnani_source,
    evon_source: form.evon_source,
    resource_consent: true,
  };
  if (form.gnani_source === 'own' && form.gnani_api_key.trim())
    body.gnani_api_key = form.gnani_api_key.trim();
  if (form.evon_source === 'own') {
    body.evon_base_url = form.evon_base_url.trim();
    body.evon_model = form.evon_model.trim();
    for (const key of ['evon_api_key', 'evon_modal_key', 'evon_modal_secret'] as const)
      if (form[key].trim()) body[key] = form[key].trim();
  }
  return body;
}

export const reviewerAccess = () => request<ReviewerAccess>('/reviewer/access');
export const requestReviewerAccess = () =>
  request<ReviewerAccess>('/reviewer/access/request', { method: 'POST' });
export const reviewerRequests = () =>
  request<{ requests: ReviewerAccessRequest[] }>('/admin/reviewer-requests');
export const decideReviewerRequest = (
  id: string,
  decision: 'approve' | 'deny' | 'revoke',
  expiresInHours: number,
  shareResources: boolean,
) =>
  request<ReviewerAccessRequest>(`/admin/reviewer-requests/${encodeURIComponent(id)}/decision`, {
    method: 'POST',
    body: JSON.stringify({
      decision,
      expires_in_hours: expiresInHours,
      share_resources: shareResources,
    }),
  });
export const reviewerWorkspace = () => request<ReviewerWorkspace>('/reviewer/workspace');
export const saveReviewerWorkspace = (form: ResourceForm) =>
  request<ReviewerWorkspace>('/reviewer/workspace', {
    method: 'POST',
    body: JSON.stringify(resourcePayload(form)),
  });

export type PreparationStatus = {
  available: boolean;
  can_prepare: boolean;
  state: 'idle' | 'starting' | 'ready' | 'unavailable' | 'disabled' | 'external';
  preparation_active?: boolean;
  preparation_expires_at?: string | null;
  preparation_remaining_seconds?: number | null;
  elapsed_ms?: number | null;
  startup_ms?: number | null;
  observed_at?: string | null;
  detail?: string;
};
export const preparationStatus = (code: string) =>
  request<PreparationStatus>(`/rooms/${encodeURIComponent(code)}/preparation`, {
    cache: 'no-store',
  });

export function preparationLabel(status: PreparationStatus | null) {
  if (!status) return 'Readiness has not been measured.';
  if (!status.available)
    return status.detail || 'Pre-meeting preparation is unavailable for this room.';
  switch (status.state) {
    case 'ready':
      return 'Translation engine responded. Ready to continue.';
    case 'starting':
      return 'Preparing the translation engine…';
    case 'unavailable':
      return 'The translation engine is unavailable. Check the selected service and retry.';
    case 'disabled':
      return 'Pre-meeting GPU preparation is disabled for this service.';
    case 'external':
      return 'External engine selected. Readiness has not been measured.';
    default:
      return 'Prepare translation before people start talking.';
  }
}
