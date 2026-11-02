import type { Membership, Participant } from '../types/domain';
import type { ConferenceReadiness } from './conferenceReadiness';
import { ConferenceRequestError } from './conferenceReadiness';

/** Deduplicate StrictMode/reconnect mutes and settle old mutes before a new unmute. */
export class MeetingMuteBarrier {
  private pending = new Map<string, Promise<Participant>>();
  constructor(private update: (membership: Membership) => Promise<Participant>) {}
  mute(membership: Membership) {
    const existing = this.pending.get(membership.session_token);
    if (existing) return existing;
    const operation = this.update(membership);
    this.pending.set(membership.session_token, operation);
    const clear = () => {
      if (this.pending.get(membership.session_token) === operation)
        this.pending.delete(membership.session_token);
    };
    void operation.then(clear, clear);
    return operation;
  }
  async wait(membership: Membership) {
    try {
      await this.pending.get(membership.session_token);
    } catch {
      /* A fresh readiness request will verify the room. */
    }
  }
}

/** Server authorization precedes capture. Failures stop the captured session, never a later one. */
export async function changeMeetingMicrophone(options: {
  muted: boolean;
  media: { setMuted: (muted: boolean) => Promise<void> };
  readiness: () => Promise<ConferenceReadiness>;
  update: (muted: boolean) => Promise<Participant>;
  isCurrent: () => boolean;
}): Promise<Participant> {
  const { media, update, readiness, isCurrent, muted } = options;
  if (muted) {
    // The media owner stops hardware synchronously; a lost unpublish ACK must
    // not delay the server mute and keep recognition running.
    try {
      void media.setMuted(true).catch(() => {});
    } catch {
      /* Still close server speech. */
    }
    return update(true);
  }
  let serverAttempted = false;
  try {
    const report = await readiness();
    if (!isCurrent())
      throw new ConferenceRequestError(
        'The media connection changed. Unmute again after reconnecting.',
        0,
      );
    if (!report.microphone.can_unmute)
      throw new ConferenceRequestError(
        report.microphone.detail,
        409,
        report.microphone.reason_code,
      );
    serverAttempted = true;
    const participant = await update(false);
    if (!isCurrent())
      throw new ConferenceRequestError(
        'The media connection changed. Unmute again after reconnecting.',
        0,
      );
    await media.setMuted(false);
    if (!isCurrent())
      throw new ConferenceRequestError(
        'The media connection changed. Unmute again after reconnecting.',
        0,
      );
    return participant;
  } catch (error) {
    try {
      void media.setMuted(true).catch(() => {});
    } catch {
      /* Session cleanup is handled by the media owner. */
    }
    if (serverAttempted)
      try {
        await update(true);
      } catch {
        /* Local capture is already stopped. */
      }
    throw error;
  }
}
