import { Track } from 'livekit-client';
import { captureMeetingCamera } from './localMediaCapture';
import type {
  LocalVideoTrack,
  RemoteVideoTrack,
  RemoteTrackPublication,
  Room,
} from 'livekit-client';
import { CAMERA_OFF, cameraError } from './cameraState';
import type { CameraState } from './cameraState';

export { CAMERA_OFF, cameraError } from './cameraState';
export type { CameraState } from './cameraState';

export type CameraTrack = LocalVideoTrack | RemoteVideoTrack;
export interface CameraEvents {
  track: (participantId: string, track: CameraTrack | null) => void;
  state: (state: CameraState) => void;
}

export function shouldSubscribeCamera(
  publication: Pick<RemoteTrackPublication, 'kind' | 'source' | 'trackName'>,
  owner: string,
  self: string,
  agent: string,
): boolean {
  return (
    owner !== self &&
    owner !== agent &&
    !!owner &&
    publication.kind === Track.Kind.Video &&
    publication.source === Track.Source.Camera &&
    publication.trackName === `camera:${owner}`
  );
}

export function cameraPermissions(peers: string[], agent: string, cameraSid?: string) {
  return [
    { participantIdentity: agent, allowAll: true },
    ...[...new Set(peers)]
      .filter((id) => id && id !== agent)
      .map((id) => ({
        participantIdentity: id,
        allowAll: false,
        allowedTrackSids: cameraSid ? [cameraSid] : [],
      })),
  ];
}

/** Capture is invoked only by setEnabled(true), never by construction or room events. */
export class MeetingCamera {
  private local: LocalVideoTrack | undefined;
  private cameraSid: string | undefined;
  private closed = false;
  private generation = 0;
  private pending = false;
  private ended: (() => void) | undefined;
  private remote = new Map<string, { sid: string; track: RemoteVideoTrack }>();

  constructor(
    private room: Pick<Room, 'localParticipant' | 'remoteParticipants'>,
    private self: string,
    private agent: string,
    private events: CameraEvents,
    private capture = captureMeetingCamera,
  ) {}

  refreshPermissions() {
    if (this.closed) return;
    this.room.localParticipant.setTrackSubscriptionPermissions(
      false,
      cameraPermissions([...this.room.remoteParticipants.keys()], this.agent, this.cameraSid),
    );
  }

  localPublished(track: unknown, sid: string) {
    if (track !== this.local || !this.local || this.closed) return;
    this.cameraSid = sid;
    this.refreshPermissions();
  }

  localUnpublished(track: unknown) {
    if (track !== this.local || !this.local) return;
    this.generation++;
    this.releaseLocal();
    this.pending = false;
    this.events.state({
      ...CAMERA_OFF,
      error: 'Camera sharing ended. Turn the camera on to try again.',
    });
  }

  remoteSubscribed(track: RemoteVideoTrack, sid: string, owner: string) {
    if (this.closed) return;
    this.remote.set(owner, { sid, track });
    this.events.track(owner, track);
  }

  remoteRemoved(sid: string, owner: string) {
    if (this.remote.get(owner)?.sid !== sid) return;
    this.remote.delete(owner);
    this.events.track(owner, null);
  }

  participantLeft(owner: string) {
    if (this.remote.delete(owner)) this.events.track(owner, null);
    this.refreshPermissions();
  }

  private releaseLocal() {
    const track = this.local;
    this.local = undefined;
    this.cameraSid = undefined;
    if (track) {
      if (this.ended) track.mediaStreamTrack.removeEventListener('ended', this.ended);
      track.stop();
      this.events.track(this.self, null);
    }
    this.ended = undefined;
    try {
      this.refreshPermissions();
    } catch {
      // The stopped camera cannot send media through a stale camera SID.
      // Continue unpublishing and updating the off state when signaling is lost.
    }
    return track;
  }

  async setEnabled(enabled: boolean): Promise<void> {
    if (this.closed && enabled) throw new Error('Reconnect media before turning on your camera.');
    if (enabled && this.local && !this.pending) return;
    if (enabled && this.pending) return;
    const version = ++this.generation;
    if (!enabled) {
      const local = this.releaseLocal();
      this.pending = false;
      this.events.state({ ...CAMERA_OFF });
      if (local) await this.room.localParticipant.unpublishTrack(local);
      return;
    }
    this.pending = true;
    this.events.state({ enabled: false, pending: true, error: '' });
    let created: LocalVideoTrack | undefined;
    try {
      created = await this.capture({
        facingMode: 'user',
        width: 640,
        height: 360,
        frameRate: 24,
      });
      if (this.closed || version !== this.generation) {
        created.stop();
        return;
      }
      this.local = created;
      this.ended = () => {
        void this.setEnabled(false).catch(() => {});
      };
      created.mediaStreamTrack.addEventListener('ended', this.ended, { once: true });
      const publication = await this.room.localParticipant.publishTrack(created, {
        name: `camera:${this.self}`,
        source: Track.Source.Camera,
        videoCodec: 'vp8',
        simulcast: true,
      });
      if (this.closed || version !== this.generation) {
        created.stop();
        await this.room.localParticipant.unpublishTrack(created);
        return;
      }
      this.cameraSid = publication.trackSid;
      this.refreshPermissions();
      this.events.track(this.self, created);
      this.events.state({ enabled: true, pending: false, error: '' });
    } catch (error) {
      if (version === this.generation && !this.closed) {
        const local = this.releaseLocal();
        if (local) void this.room.localParticipant.unpublishTrack(local).catch(() => {});
        else created?.stop();
        this.events.state({ ...CAMERA_OFF, error: cameraError(error) });
        throw new Error(cameraError(error));
      }
    } finally {
      if (version === this.generation) this.pending = false;
    }
  }

  async disconnect() {
    if (this.closed) return;
    this.closed = true;
    this.generation++;
    const local = this.releaseLocal();
    this.pending = false;
    this.remote.forEach((_value, owner) => this.events.track(owner, null));
    this.remote.clear();
    this.events.state({ ...CAMERA_OFF });
    // Hardware is stopped above. A lost signaling acknowledgement must not
    // prevent the owning room from disconnecting and the user from leaving.
    if (local) void this.room.localParticipant.unpublishTrack(local).catch(() => {});
  }
}
