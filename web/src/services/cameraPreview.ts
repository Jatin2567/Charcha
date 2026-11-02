import { cameraError } from './cameraState';

export interface PreviewState {
  stream: MediaStream | null;
  pending: boolean;
  error: string;
}
export class CameraPreviewController {
  private stream: MediaStream | null = null;
  private generation = 0;
  private closed = false;
  private pending = false;
  private ended: (() => void) | undefined;
  constructor(
    private changed: (state: PreviewState) => void,
    private capture: (constraints: MediaStreamConstraints) => Promise<MediaStream>,
  ) {}
  stop() {
    this.generation++;
    if (this.stream) {
      if (this.ended)
        this.stream.getVideoTracks().forEach((t) => t.removeEventListener('ended', this.ended!));
      this.stream.getTracks().forEach((t) => t.stop());
    }
    this.stream = null;
    this.ended = undefined;
    this.pending = false;
    if (!this.closed) this.changed({ stream: null, pending: false, error: '' });
  }
  async start() {
    if (this.closed || this.pending || this.stream) return;
    const version = ++this.generation;
    this.pending = true;
    this.changed({ stream: null, pending: true, error: '' });
    try {
      const stream = await this.capture({
        audio: false,
        video: {
          width: { ideal: 640 },
          height: { ideal: 360 },
          frameRate: { ideal: 24 },
          facingMode: 'user',
        },
      });
      if (this.closed || version !== this.generation) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      this.stream = stream;
      this.ended = () => this.stop();
      stream
        .getVideoTracks()
        .forEach((t) => t.addEventListener('ended', this.ended!, { once: true }));
      this.changed({ stream, pending: false, error: '' });
    } catch (e) {
      if (!this.closed && version === this.generation)
        this.changed({ stream: null, pending: false, error: cameraError(e) });
    } finally {
      if (version === this.generation) this.pending = false;
    }
  }
  close() {
    this.closed = true;
    this.stop();
  }
}
