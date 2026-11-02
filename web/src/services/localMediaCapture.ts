import { LocalAudioTrack, LocalVideoTrack, Track } from 'livekit-client';

/** Keep reacquisition under the meeting controls, including after device loss.
 * SDK-managed tracks may restart on a default device when their capture ends.
 */
async function captureOwnedTrack<T>(
  kind: 'audio' | 'video',
  constraints: MediaTrackConstraints,
  wrap: (track: MediaStreamTrack) => T,
): Promise<T> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: kind === 'audio' ? constraints : false,
    video: kind === 'video' ? constraints : false,
  });
  const tracks = stream.getTracks();
  const selected = tracks.find((track) => track.kind === kind);
  try {
    if (!selected) throw new Error(`No ${kind} track was captured.`);
    const track = wrap(selected);
    tracks.filter((other) => other !== selected).forEach((other) => other.stop());
    return track;
  } catch (error) {
    tracks.forEach((track) => track.stop());
    throw error;
  }
}

export function captureMeetingMicrophone(constraints: MediaTrackConstraints) {
  return captureOwnedTrack('audio', constraints, (raw) => {
    const track = new LocalAudioTrack(raw, constraints, true);
    track.source = Track.Source.Microphone;
    return track;
  });
}

export function captureMeetingCamera(constraints: MediaTrackConstraints) {
  return captureOwnedTrack('video', constraints, (raw) => {
    const track = new LocalVideoTrack(raw, constraints, true);
    track.source = Track.Source.Camera;
    return track;
  });
}
