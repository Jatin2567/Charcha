import { request } from './api';

export type ReviewerAccess = {
  reviewer: boolean;
  can_host: boolean;
  reviewer_shared_allowed: boolean;
  expires_at?: number | null;
};
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
