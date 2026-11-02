/** Camera UI state and browser error copy. No media SDK or device access. */
export interface CameraState {
  enabled: boolean;
  pending: boolean;
  error: string;
}

export const CAMERA_OFF: CameraState = { enabled: false, pending: false, error: '' };

export function cameraError(error: unknown): string {
  const name = error && typeof error === 'object' && 'name' in error ? error.name : '';
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError')
    return 'Camera permission was denied. Allow camera access for this site, then try again.';
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError')
    return 'No camera was found. Connect a camera and try again.';
  if (name === 'NotReadableError' || name === 'TrackStartError')
    return 'The camera is unavailable or in use by another app. Close that app and try again.';
  if (name === 'SecurityError') return 'Camera access requires HTTPS or localhost.';
  return 'The camera could not start. Check camera permissions and reconnect if needed.';
}
