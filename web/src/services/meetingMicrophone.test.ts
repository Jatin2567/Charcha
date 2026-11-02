import { describe, expect, it } from 'vitest';
import { changeMeetingMicrophone, MeetingMuteBarrier } from './meetingMicrophone';
import type { ConferenceReadiness } from './conferenceReadiness';
import type { Membership, Participant } from '../types/domain';

const report = (allowed = true) =>
  ({
    microphone: {
      can_unmute: allowed,
      reason_code: 'provider_flow_locked',
      detail: 'An operator-approved flow is required.',
    },
    provider_flow: { required: true, status: 'approved' },
  }) as ConferenceReadiness;
const participant = (muted: boolean) => ({ id: 'self', muted }) as Participant;

describe('explicit meeting microphone transition', () => {
  it('deduplicates StrictMode mutes and waits for the right membership before unmuting', async () => {
    const callbacks = new Map<string, (value: Participant) => void>();
    const calls: string[] = [];
    const barrier = new MeetingMuteBarrier((member) => {
      calls.push(member.session_token);
      return new Promise<Participant>((resolve) => callbacks.set(member.session_token, resolve));
    });
    const first = { session_token: 'first' } as Membership,
      second = { session_token: 'second' } as Membership;
    const pending = barrier.mute(first);
    expect(barrier.mute(first)).toBe(pending);
    barrier.mute(second);
    expect(calls).toEqual(['first', 'second']);
    let firstReady = false,
      secondReady = false;
    const a = barrier.wait(first).then(() => {
      firstReady = true;
    });
    const b = barrier.wait(second).then(() => {
      secondReady = true;
    });
    callbacks.get('first')!(participant(true));
    await a;
    expect(firstReady).toBe(true);
    expect(secondReady).toBe(false);
    callbacks.get('second')!(participant(true));
    await b;
    expect(secondReady).toBe(true);
  });
  it('authorizes on the server before touching capture, including fresh readiness', async () => {
    const events: string[] = [];
    await changeMeetingMicrophone({
      muted: false,
      readiness: async () => {
        events.push('read');
        return report();
      },
      update: async (muted) => {
        events.push(`server:${muted}`);
        return participant(muted);
      },
      media: {
        setMuted: async (muted) => {
          events.push(`media:${muted}`);
        },
      },
      isCurrent: () => true,
    });
    expect(events).toEqual(['read', 'server:false', 'media:false']);
  });

  it('does not open a device or request server unmute when a fresh check is locked', async () => {
    const events: string[] = [];
    await expect(
      changeMeetingMicrophone({
        muted: false,
        readiness: async () => report(false),
        update: async (muted) => {
          events.push(`server:${muted}`);
          return participant(muted);
        },
        media: {
          setMuted: async (muted) => {
            events.push(`media:${muted}`);
          },
        },
        isCurrent: () => true,
      }),
    ).rejects.toThrow('operator-approved');
    expect(events).not.toContain('media:false');
    expect(events).not.toContain('server:false');
  });

  it('allows the explicit cost-free original-audio path without inventing a paid approval', async () => {
    const original = report();
    original.provider_flow = { ...original.provider_flow, required: false, status: 'not_required' };
    const changes: boolean[] = [];
    await changeMeetingMicrophone({
      muted: false,
      readiness: async () => original,
      update: async (muted) => participant(muted),
      media: {
        setMuted: async (muted) => {
          changes.push(muted);
        },
      },
      isCurrent: () => true,
    });
    expect(changes).toEqual([false]);
  });

  it('rolls back the captured session and server state when microphone permission fails', async () => {
    const events: string[] = [];
    await expect(
      changeMeetingMicrophone({
        muted: false,
        readiness: async () => report(),
        update: async (muted) => {
          events.push(`server:${muted}`);
          return participant(muted);
        },
        media: {
          setMuted: async (muted) => {
            events.push(`media:${muted}`);
            if (!muted) throw new Error('Permission denied');
          },
        },
        isCurrent: () => true,
      }),
    ).rejects.toThrow('Permission denied');
    expect(events).toEqual(['server:false', 'media:false', 'media:true', 'server:true']);
  });

  it('sends a closing mute when an unmute acknowledgement is lost before capture starts', async () => {
    const events: string[] = [];
    await expect(
      changeMeetingMicrophone({
        muted: false,
        readiness: async () => report(),
        update: async (muted) => {
          events.push(`server:${muted}`);
          if (!muted) throw new Error('Response lost');
          return participant(muted);
        },
        media: {
          setMuted: async (muted) => {
            events.push(`media:${muted}`);
          },
        },
        isCurrent: () => true,
      }),
    ).rejects.toThrow('Response lost');
    expect(events).toEqual(['server:false', 'media:true', 'server:true']);
    expect(events).not.toContain('media:false');
  });

  it('never opens a stale connection after a concurrent reconnect', async () => {
    const events: string[] = [];
    let current = true;
    await expect(
      changeMeetingMicrophone({
        muted: false,
        readiness: async () => report(),
        update: async (muted) => {
          events.push(`server:${muted}`);
          if (!muted) current = false;
          return participant(muted);
        },
        media: {
          setMuted: async (muted) => {
            events.push(`media:${muted}`);
          },
        },
        isCurrent: () => current,
      }),
    ).rejects.toThrow('connection changed');
    expect(events).toEqual(['server:false', 'media:true', 'server:true']);
  });

  it('always mutes the server without waiting for unpublish or consulting paid-flow readiness', async () => {
    const events: string[] = [];
    const value = await changeMeetingMicrophone({
      muted: true,
      readiness: async () => {
        throw new Error('Readiness must not gate mute');
      },
      update: async (muted) => {
        events.push(`server:${muted}`);
        return participant(muted);
      },
      media: {
        setMuted: (muted) => {
          events.push(`media:${muted}`);
          return new Promise<void>(() => {});
        },
      },
      isCurrent: () => true,
    });
    expect(events).toEqual(['media:true', 'server:true']);
    expect(value.muted).toBe(true);
  });
});
