import { describe, expect, it } from 'vitest';
import { createDemoRoom, demoLookup, joinDemo, makeDemoTurn, SCRIPTED_TURNS } from './demo';
describe('honest standalone demo', () => {
  it('identifies every canned participant as a sample and the joining person as human', () => {
    const room = createDemoRoom('Demo');
    const membership = joinDemo(room.code, 'Aditi', 'en', 'standard');
    expect(membership.localDemo).toBe(true);
    expect(membership.livekit).toBeNull();
    expect(membership.room.mode).toBe('demo');
    expect(membership.room.participants.filter((p) => p.is_demo)).toHaveLength(3);
    expect(membership.participant.is_demo).toBe(false);
  });
  it('does not fabricate translations for unknown input', () =>
    expect(demoLookup('An arbitrary sentence never in the script', 'ta')).toBeNull());
  it('only looks up a known script sentence across its reviewed target languages', () =>
    expect(demoLookup(SCRIPTED_TURNS[1].text, 'en')).toBe(
      'Yes. We need 50 cartons at ₹1,500 each.',
    ));
  it('never preconfirms sample content on behalf of a human', () =>
    expect(makeDemoTurn(1).confirmed_by).toEqual([]));
  it('supports retrieving the same-language source without a fabricated translation', () =>
    expect(demoLookup(SCRIPTED_TURNS[0].text, 'hi')).toBe(SCRIPTED_TURNS[0].text));
});
