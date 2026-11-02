import { API_BASE } from './api';
import type { ReadinessReport } from '../types/performance';

export const DEPLOYMENT_FIELDS = [
  {
    key: 'GNANI_API_KEY',
    label: 'Gnani speech access',
    required: true,
    detail:
      'Prisma recognition, Timbre synthesis and consented voice embeddings. Confirm access and remaining allowance with Gnani.',
  },
  {
    key: 'LIVEKIT_URL',
    label: 'Secure media address',
    required: true,
    detail: 'The browser-reachable wss://media address on your own server.',
  },
  {
    key: 'LIVEKIT_API_KEY',
    label: 'Local LiveKit signing key',
    required: true,
    detail: 'Generated for your self-hosted server; a LiveKit Cloud subscription is unnecessary.',
  },
  {
    key: 'LIVEKIT_API_SECRET',
    label: 'Local LiveKit signing secret',
    required: true,
    detail: 'Generated and kept on the server, together with the signing key.',
  },
  {
    key: 'EVON_BASE_URL',
    label: 'Evon inference address',
    required: true,
    detail:
      'An actual running, OpenAI-compatible /v1 endpoint, supplied by an approved host or your GPU deployment.',
  },
  {
    key: 'EVON_MODEL',
    label: 'Evon served model',
    required: true,
    detail:
      'The exact model identifier exposed by that endpoint. A beta invitation alone does not confirm API compatibility.',
  },
  {
    key: 'EVON_API_KEY',
    label: 'Evon endpoint authentication',
    required: false,
    detail:
      'Required when the inference endpoint uses an access key. Keep it in the server environment.',
  },
  {
    key: 'TIMBRE_MODEL',
    label: 'Speech model override',
    required: false,
    detail:
      'A default is included. Override it only if your account requires a different supported model.',
  },
  {
    key: 'TIMBRE_VOICE',
    label: 'Standard voice override',
    required: false,
    detail: 'A default is included. Voice cloning uses a separate, explicitly consented reference.',
  },
] as const;

export type DeploymentFieldKey = (typeof DEPLOYMENT_FIELDS)[number]['key'];
export interface DeploymentSnapshot extends Pick<ReadinessReport, 'mode' | 'generated_at'> {
  fields: { key: DeploymentFieldKey; configured: boolean | null }[];
  configuration_issues: { key: string; detail: string }[];
}

const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

/** Readiness is configuration evidence only. Retain no raw fields, values or credentials. */
export function validateDeployment(value: unknown): DeploymentSnapshot {
  if (
    !object(value) ||
    !['live', 'demo', 'transport'].includes(String(value.mode)) ||
    typeof value.generated_at !== 'string' ||
    !Number.isFinite(Date.parse(value.generated_at)) ||
    value.provider_verification !== 'not_checked' ||
    !Array.isArray(value.requirements)
  )
    throw new Error('Invalid deployment readiness report.');

  const configured = new Map<string, boolean>();
  const known = new Set<string>(DEPLOYMENT_FIELDS.map((field) => field.key));
  for (const field of value.requirements) {
    if (!object(field) || typeof field.key !== 'string')
      throw new Error('Invalid deployment readiness report.');
    if (!known.has(field.key)) continue;
    if (typeof field.configured !== 'boolean' || configured.has(field.key))
      throw new Error('Invalid deployment readiness report.');
    configured.set(field.key, field.configured);
  }
  if (DEPLOYMENT_FIELDS.some((field) => field.required && !configured.has(field.key)))
    throw new Error('Incomplete deployment readiness report.');

  const issueKeys = new Set<string>([
    ...known,
    'ARTHA_MODE',
    'LIVEKIT_INTERNAL_URL',
    'GNANI_STT_URL',
    'GNANI_TTS_URL',
    'GNANI_EMBEDDING_URL',
    'CORS_ORIGINS',
    'USAGE_REQUIRE_FLOW_APPROVAL',
    'USAGE_SHOW_PRIVATE_BALANCE',
  ]);
  const issues = value.configuration_issues ?? [];
  if (!Array.isArray(issues)) throw new Error('Invalid deployment readiness report.');
  const configuration_issues: DeploymentSnapshot['configuration_issues'] = [];
  for (const issue of issues) {
    if (
      !object(issue) ||
      typeof issue.key !== 'string' ||
      typeof issue.detail !== 'string' ||
      issue.detail.length > 500
    )
      throw new Error('Invalid deployment readiness report.');
    if (issueKeys.has(issue.key))
      configuration_issues.push({ key: issue.key, detail: issue.detail });
  }

  return {
    mode: value.mode as DeploymentSnapshot['mode'],
    generated_at: value.generated_at,
    fields: DEPLOYMENT_FIELDS.map((field) => ({
      key: field.key,
      configured: configured.get(field.key) ?? null,
    })),
    configuration_issues,
  };
}

export async function fetchDeployment(signal: AbortSignal): Promise<DeploymentSnapshot> {
  const response = await fetch(`${API_BASE}/readiness`, {
    method: 'GET',
    cache: 'no-store',
    signal,
  });
  if (!response.ok) throw new Error('Deployment readiness is unavailable.');
  return validateDeployment(await response.json());
}
