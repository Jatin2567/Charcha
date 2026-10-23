import { describe, expect, it } from 'vitest';
import { initialRoomState, roomReducer } from './roomReducer';
import { createDemoRoom, demoEvent, makeDemoTurn } from '../services/demo';

describe('authoritative recovery and early captions', () => {
  it('clears stale pipeline errors and speaker activity after reconnect', () => {
    const recovered = roomReducer(
      { ...initialRoomState, error: 'Old outage', stages: { departed: 'speaking' } },
      demoEvent('room.snapshot', { room: createDemoRoom('Recovered'), turns: [], metrics: null }),
    );
    expect(recovered.error).toBe('');
    expect(recovered.stages).toEqual({});
  });

  it('makes translated text visible without declaring unfinished audio work complete', () => {
    const turn = { ...makeDemoTurn(0), status: 'processing' as const };
    const state = roomReducer(
      { ...initialRoomState, turns: [turn] },
      demoEvent('translation.ready', {
        utterance_id: turn.id,
        target_language: 'ta',
        text: 'Ready before audio finishes',
      }),
    );
    expect(state.turns[0].translations.ta).toBe('Ready before audio finishes');
    expect(state.turns[0].status).toBe('processing');
  });
});
