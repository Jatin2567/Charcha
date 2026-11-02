import { useEffect, useRef, useState } from 'react';
import { CameraPreviewController } from '../services/cameraPreview';
import type { PreviewState } from '../services/cameraPreview';

export function useCameraPreview() {
  const [state, setState] = useState<PreviewState>({ stream: null, pending: false, error: '' });
  const controller = useRef<CameraPreviewController | null>(null);
  useEffect(() => {
    const current = new CameraPreviewController(setState, (constraints) => {
      if (!navigator.mediaDevices?.getUserMedia) return Promise.reject({ name: 'SecurityError' });
      return navigator.mediaDevices.getUserMedia(constraints);
    });
    controller.current = current;
    return () => {
      current.close();
      controller.current = null;
    };
  }, []);
  return {
    ...state,
    start: () => controller.current?.start(),
    stop: () => controller.current?.stop(),
  };
}
