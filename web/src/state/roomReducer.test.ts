import { describe, expect, it } from 'vitest';
import { initialRoomState, roomReducer } from './roomReducer';
import type { RoomState } from './roomReducer';
import { createDemoRoom, demoEvent, joinDemo, makeDemoTurn } from '../services/demo';
describe('room event state', () => {
  it('replaces a reconnect snapshot without duplicating transcript turns', () => {
    const room = createDemoRoom('Order review');
    const turn = makeDemoTurn(0);
    let state = roomReducer(
      initialRoomState,
      demoEvent('room.snapshot', { room, turns: [turn], metrics: null }),
    );
    state = roomReducer(state, demoEvent('room.snapshot', { room, turns: [turn], metrics: null }));
    expect(state.turns).toHaveLength(1);
    expect(state.room?.title).toBe('Order review');
  });
  it('upserts a transcript revision using its stable utterance identity', () => {
    const turn = makeDemoTurn(0);
    const state = roomReducer(
      { ...initialRoomState, turns: [{ ...turn, status: 'processing' }] },
      demoEvent('transcript.final', { turn: { ...turn, text: 'Corrected amount' } }),
    );
    expect(state.turns).toHaveLength(1);
    expect(state.turns[0].text).toBe('Corrected amount');
  });
  it('merges target translations without losing another listening language', () => {
    const turn = makeDemoTurn(0);
    const state = roomReducer(
      { ...initialRoomState, turns: [turn] },
      demoEvent('translation.ready', {
        utterance_id: turn.id,
        target_language: 'en',
        text: 'Revised translation',
      }),
    );
    expect(state.turns[0].translations.en).toBe('Revised translation');
    expect(state.turns[0].translations.ta).toBe(turn.translations.ta);
  });
  it('tracks only actual confirmation identities from the event', () => {
    const turn = makeDemoTurn(1);
    const state = roomReducer(
      { ...initialRoomState, turns: [turn] },
      demoEvent('confirmation.updated', { utterance_id: turn.id, confirmed_by: ['human-1'] }),
    );
    expect(state.turns[0].confirmed_by).toEqual(['human-1']);
  });
  it('upserts participant updates and removes a departed participant', () => {
    const room = createDemoRoom('People');
    const membership = joinDemo(room.code, 'Aditi', 'en', 'standard');
    let state: RoomState = { ...initialRoomState, room: membership.room };
    state = roomReducer(
      state,
      demoEvent('participant.updated', {
        participant: { ...membership.participant, muted: false },
      }),
    );
    expect(state.room?.participants.filter((p) => p.id === membership.participant.id)).toHaveLength(
      1,
    );
    state = roomReducer(
      state,
      demoEvent('participant.left', { participant_id: membership.participant.id }),
    );
    expect(state.room?.participants.some((p) => p.id === membership.participant.id)).toBe(false);
  });
  it('keeps a pipeline failure visible and marks demo completion explicitly', () => {
    let state = roomReducer(
      initialRoomState,
      demoEvent('pipeline.error', { message: 'Provider unavailable', retryable: true }),
    );
    expect(state.error).toBe('Provider unavailable');
    state = roomReducer(state, demoEvent('demo.complete', {}));
    expect(state.demoComplete).toBe(true);
  });
  it('ignores unknown events without destroying the current state', () => {
    expect(roomReducer(initialRoomState, demoEvent('future.event', {}))).toBe(initialRoomState);
  });
});
