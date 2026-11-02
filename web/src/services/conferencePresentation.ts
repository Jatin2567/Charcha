import type { ConferenceReadiness } from './conferenceReadiness';

/** Uses the server snapshot and monotonic elapsed time, rather than the laptop's wall clock. */
export function approvalSeconds(report: ConferenceReadiness | null, elapsedSeconds = 0) {
  if (!report?.generated_at || !report.provider_flow.expires_at) return null;
  const seconds =
    (Date.parse(report.provider_flow.expires_at) - Date.parse(report.generated_at)) / 1000;
  return Number.isFinite(seconds)
    ? Math.max(0, Math.floor(seconds - Math.max(0, elapsedSeconds)))
    : null;
}
/** Status label that never reads "approved" once the window has elapsed. */
export function approvalLabel(status: string, seconds: number | null) {
  if (status === 'approved' && seconds === 0) return 'expired';
  return status.replaceAll('_', ' ');
}
export function timeLeft(seconds: number | null) {
  if (seconds === null) return 'Time remaining unavailable';
  if (seconds === 0) return 'Approval window elapsed';
  return `About ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')} remaining`;
}
export function conferenceTitle(
  report: ConferenceReadiness | null,
  muted: boolean,
  stale: boolean,
  mediaReady: boolean,
  seconds: number | null,
) {
  if (stale) return 'Rejoin this conversation';
  if (!mediaReady) return 'Connecting your media';
  if (!muted) return 'Your microphone is on';
  if (report?.microphone.reason_code === 'provider_configuration_missing')
    return 'Interpretation needs configuration';
  if (report?.provider_flow.required) {
    const titles = {
      locked: 'Interpretation is waiting for operator approval',
      expired: 'Interpretation approval has expired',
      exhausted: 'Interpretation allowance is used up',
      unavailable: 'Interpretation approval is unavailable',
    };
    const status = report.provider_flow.status;
    if (status in titles) return titles[status as keyof typeof titles];
    if (status === 'approved' && seconds === 0) return 'Interpretation approval has expired';
  }
  return report?.microphone.can_unmute ? 'Ready when you are' : 'Microphone is paused';
}
