import { useEffect, useRef, useState } from 'react';
import type { CameraTrack } from '../services/meetingVideo';
import './CameraVideo.css';

/** Video stays muted: all participant audio comes through the language-specific audio path. */
export function CameraVideo({
  track,
  self,
  name,
}: {
  track: CameraTrack;
  self: boolean;
  name: string;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  const [blocked, setBlocked] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    let active = true;
    element.muted = true;
    track.attach(element);
    void element.play().then(
      () => {
        if (active) setBlocked(false);
      },
      () => {
        if (active) setBlocked(true);
      },
    );
    return () => {
      active = false;
      track.detach(element);
      element.srcObject = null;
    };
  }, [track]);
  return (
    <div className="camera-video-wrap">
      <video
        ref={ref}
        autoPlay
        playsInline
        muted
        className={`camera-video ${self ? 'camera-mirrored' : ''}`}
        aria-label={`${name}${self ? ' — your camera preview' : ' — live camera'}`}
      />
      {blocked && (
        <button
          className="camera-play"
          onClick={() =>
            void ref.current?.play().then(
              () => setBlocked(false),
              () => setBlocked(true),
            )
          }
        >
          Play video
        </button>
      )}
    </div>
  );
}

export function LocalCameraPreview({ stream }: { stream: MediaStream }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    element.srcObject = stream;
    void element.play().catch(() => {});
    return () => {
      element.srcObject = null;
    };
  }, [stream]);
  return (
    <div className="camera-preview-wrap">
      <video ref={ref} muted autoPlay playsInline aria-label="Your private camera preview" />
    </div>
  );
}
