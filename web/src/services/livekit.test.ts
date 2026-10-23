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
