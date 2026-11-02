import { describe, expect, it } from 'vitest';
import { shouldSubscribe } from './livekit';
describe('translated audio subscription filter', () => {
  it('accepts a translated track from the room agent in the selected language', () =>
    expect(shouldSubscribe('translated:other:ta', 'agent', 'self', 'ta', 'agent')).toBe(true));
  it.each([
    ['source:other', 'other', 'self', 'ta', 'agent'],
    ['translated:other:ta', 'untrusted-participant', 'self', 'ta', 'agent'],
    ['translated:self:ta', 'agent', 'self', 'ta', 'agent'],
    ['translated:other:hi', 'agent', 'self', 'ta', 'agent'],
    ['translated:other:ta:extra', 'agent', 'self', 'ta', 'agent'],
    ['translated', 'agent', 'self', 'ta', 'agent'],
  ])('rejects an unauthorized or irrelevant publication %s', (...args) =>
    expect(shouldSubscribe(args[0], args[1], args[2], args[3] as 'ta', args[4])).toBe(false),
  );
});

describe('explicit raw audio transport isolation', () => {
  it('accepts another speaker’s raw agent relay only in transport mode', () => {
    expect(shouldSubscribe('raw:other:all', 'agent', 'self', 'ta', 'agent', 'transport')).toBe(true);
    expect(shouldSubscribe('raw:other:all', 'agent', 'self', 'ta', 'agent', 'live')).toBe(false);
    expect(shouldSubscribe('raw:other:all', 'agent', 'self', 'ta', 'agent', 'demo')).toBe(false);
  });
  it.each([
    ['raw:self:all', 'agent'],
    ['raw:other:all', 'other'],
    ['raw::all', 'agent'],
    ['raw:other:ta', 'agent'],
    ['raw:other:all:extra', 'agent'],
    ['source:other', 'other'],
    ['translated:other:ta', 'agent'],
  ])('rejects self, direct, translated or malformed raw publication %s', (track, owner) => {
    expect(shouldSubscribe(track, owner, 'self', 'ta', 'agent', 'transport')).toBe(false);
  });
});

describe('dedicated receiver probe routing', () => {
  const track = 'probe:unique_probe_123456789012:self';
  it('allows a private probe from the room agent in real audio modes', () => {
    expect(shouldSubscribe(track, 'agent', 'self', 'ta', 'agent', 'transport')).toBe(true);
    expect(shouldSubscribe(track, 'agent', 'self', 'ta', 'agent', 'live')).toBe(true);
  });
  it('rejects another listener, forged publisher, malformed ID and scripted mode', () => {
    expect(shouldSubscribe(track, 'agent', 'other', 'ta', 'agent', 'transport')).toBe(false);
    expect(shouldSubscribe(track, 'stranger', 'self', 'ta', 'agent', 'transport')).toBe(false);
    expect(shouldSubscribe('probe:short:self', 'agent', 'self', 'ta', 'agent', 'transport')).toBe(false);
    expect(shouldSubscribe(`${track}:extra`, 'agent', 'self', 'ta', 'agent', 'transport')).toBe(false);
    expect(shouldSubscribe(track, 'agent', 'self', 'ta', 'agent', 'demo')).toBe(false);
  });
});
