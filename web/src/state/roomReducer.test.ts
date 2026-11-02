import { describe, expect, it } from 'vitest';
import { initialRoomState, roomReducer } from './roomReducer';
import type { RoomState } from './roomReducer';
import { createDemoRoom, demoEvent, joinDemo, makeDemoTurn } from '../services/demo';
describe('room event state', () => {
  it('restores detector configuration on reconnect and clears it for older snapshots', () => {
    const room = createDemoRoom('VoiceShield configuration');
    const screeningStatus = { mode: 'monitor', model: { ready: true, window_ms: 4037.5 } };
    const state = roomReducer(initialRoomState, demoEvent('room.snapshot', {
      room, turns: [], screening: {}, screening_status: screeningStatus,
    }));
    expect(state.screeningStatus).toEqual(screeningStatus);
    expect(roomReducer(state, demoEvent('room.snapshot', { room, turns: [] })).screeningStatus).toBeNull();
  });
  it('keeps inconclusive screening distinct and clears stale results on mute or leave', () => {
    const room = createDemoRoom('Local screening state');
    const member = joinDemo(room.code, 'Local fixture', 'hi', 'standard');
    const sample = { speaker_id: member.participant.id, verdict: 'unknown', score: null, action: 'withheld' };
    let state = roomReducer({ ...initialRoomState, room: member.room }, demoEvent('screening.updated', sample));
    expect(state.screening[member.participant.id].verdict).toBe('unknown');
    const ignored = roomReducer(state, demoEvent('screening.updated', { ...sample, speaker_id: 'not-in-room' }));
    expect(ignored).toBe(state);
    state = roomReducer(state, demoEvent('participant.updated', { participant: { ...member.participant, muted: true } }));
    expect(state.screening).toEqual({});
    state = roomReducer(state, demoEvent('screening.updated', sample));
    state = roomReducer(state, demoEvent('participant.left', { participant_id: member.participant.id }));
    expect(state.screening).toEqual({});
    const restored = roomReducer(initialRoomState, demoEvent('room.snapshot', { room: member.room, turns: [], screening: { [member.participant.id]: sample } }));
    expect(restored.screening[member.participant.id].action).toBe('withheld');
  });
  it('replaces a reconnect snapshot without duplicating transcript turns', () => {
    const room = createDemoRoom('A neighbourhood meeting');
    const turn = makeDemoTurn(0);
    let state = roomReducer(
      initialRoomState,
      demoEvent('room.snapshot', { room, turns: [turn], metrics: null }),
    );
    state = roomReducer(state, demoEvent('room.snapshot', { room, turns: [turn], metrics: null }));
    expect(state.turns).toHaveLength(1);
    expect(state.room?.title).toBe('A neighbourhood meeting');
  });
  it('upserts a transcript revision using its stable utterance identity', () => {
    const turn = makeDemoTurn(0);
    const state = roomReducer(
      { ...initialRoomState, turns: [{ ...turn, status: 'processing' }] },
      demoEvent('transcript.final', { turn: { ...turn, text: 'Corrected meeting time' } }),
    );
    expect(state.turns).toHaveLength(1);
    expect(state.turns[0].text).toBe('Corrected meeting time');
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
