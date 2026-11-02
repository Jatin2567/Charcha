import { Track } from 'livekit-client';
import type { LocalAudioTrack, Room } from 'livekit-client';
import { captureMeetingMicrophone } from './localMediaCapture';

export type MicrophoneReason =
  | 'initial'
  | 'user'
  | 'reconnecting'
  | 'disconnected'
  | 'device-ended'
  | 'error';
export interface MicrophoneState {
  muted: boolean;
  reason: MicrophoneReason;
}

function microphoneError(error: unknown): string {
  const name = error && typeof error === 'object' && 'name' in error ? error.name : '';
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError')
    return 'Microphone permission was denied. Allow microphone access for this site, then try again.';
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError')
    return 'No microphone was found. Choose a connected microphone and try again.';
  if (name === 'NotReadableError' || name === 'TrackStartError')
    return 'The microphone is unavailable or in use by another app. Choose another microphone or try again.';
  if (name === 'OverconstrainedError' || name === 'ConstraintNotSatisfiedError')
    return 'The selected microphone is unavailable. Choose a connected microphone and try again.';
  return 'The microphone could not start. Check permissions and reconnect if needed.';
}

/** Every new capture requires explicit unmute; reconnect only marks readiness. */
export class MeetingMicrophone {
  private local: LocalAudioTrack | undefined;
  private ended: (() => void) | undefined;
  private generation = 0;
  private ready = false;
  private closed = false;
  private pending: Promise<void> | undefined;

  constructor(
    private room: Pick<Room, 'localParticipant'>,
    private self: string,
    private input: string,
    private changed: (state: MicrophoneState) => void,
    private capture = captureMeetingMicrophone,
  ) {}

  get track() {
    return this.local;
  }
  connected() {
    if (!this.closed) this.ready = true;
  }

  private release() {
    const track = this.local;
    this.local = undefined;
    if (track) {
      if (this.ended) track.mediaStreamTrack.removeEventListener('ended', this.ended);
      track.stop();
    }
    this.ended = undefined;
    return track;
  }

  private unpublish(track: LocalAudioTrack | undefined) {
    return track
      ? Promise.resolve().then(() => this.room.localParticipant.unpublishTrack(track))
      : Promise.resolve();
  }

  suspend(reason: 'reconnecting' | 'disconnected' | 'device-ended' | 'error') {
    if (this.closed) return;
    if (reason === 'reconnecting' || reason === 'disconnected') this.ready = false;
    this.generation++;
    const track = this.release();
    this.changed({ muted: true, reason });
    // Stop hardware before a possibly missing signaling acknowledgement.
    void this.unpublish(track).catch(() => {});
  }

  unpublished(track: unknown) {
    if (track === this.local && this.local) this.suspend('error');
  }

  setMuted(value: boolean, reason: MicrophoneReason = 'user'): Promise<void> {
    if (value) {
      if (this.closed) return Promise.resolve();
      this.generation++;
      const track = this.release();
      this.changed({ muted: true, reason });
      return this.unpublish(track).then(() => undefined);
    }
    if (this.closed || !this.ready)
      return Promise.reject(
        new Error('Audio is not connected. Reconnect before enabling your microphone.'),
      );
    if (this.local && !this.pending) return Promise.resolve();
    if (this.pending) return this.pending;
    const version = ++this.generation;
    const operation = this.enable(version, reason);
    this.pending = operation;
    const clear = () => {
      if (this.pending === operation) this.pending = undefined;
    };
    void operation.then(clear, clear);
    return operation;
  }

  private async enable(version: number, reason: MicrophoneReason) {
    let created: LocalAudioTrack | undefined;
    try {
      created = await this.capture({
        deviceId: this.input === 'default' ? undefined : { exact: this.input },
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      });
      if (this.closed || !this.ready || version !== this.generation) {
        created.stop();
        throw new Error('Microphone request cancelled.');
      }
      this.local = created;
      this.ended = () => this.suspend('device-ended');
      created.mediaStreamTrack.addEventListener('ended', this.ended, { once: true });
      await this.room.localParticipant.publishTrack(created, {
        name: `source:${this.self}`,
        source: Track.Source.Microphone,
      });
      if (this.closed || !this.ready || version !== this.generation) {
        created.stop();
        void this.unpublish(created).catch(() => {});
        throw new Error('Microphone request cancelled.');
      }
      this.changed({ muted: false, reason });
    } catch (error) {
      if (created && this.local === created) this.release();
      else created?.stop();
      void this.unpublish(created).catch(() => {});
      if (!this.closed && version === this.generation) {
        this.changed({ muted: true, reason: 'error' });
        throw new Error(microphoneError(error));
      }
      throw new Error('Microphone request cancelled.');
    }
  }

  disconnect() {
    if (this.closed) return;
    this.suspend('disconnected');
    this.closed = true;
  }
}
