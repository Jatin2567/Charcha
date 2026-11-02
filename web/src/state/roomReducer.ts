import type { AppEvent, Metrics, Participant, Room, Turn } from '../types/domain';
import type { RoomScreeningSample, RoomScreeningStatus } from '../services/localDiagnostics';
export interface RoomState {
  room: Room | null;
  turns: Turn[];
  metrics: Metrics | null;
  stages: Record<string, string>;
  error: string;
  demoComplete: boolean;
  screening: Record<string, RoomScreeningSample>;
  screeningStatus: RoomScreeningStatus | null;
}
export const initialRoomState: RoomState = {
  room: null,
  turns: [],
  metrics: null,
  stages: {},
  error: '',
  demoComplete: false,
  screening: {},
  screeningStatus: null,
};
export function roomReducer(state: RoomState, event: AppEvent): RoomState {
  const p = event.payload;
  switch (event.type) {
    case 'room.snapshot':
      return {
        ...state,
        room: p.room as Room,
        turns: p.turns as Turn[],
        metrics: (p.metrics as Metrics) || null,
        stages: {},
        screening: (p.screening as Record<string, RoomScreeningSample>) || {},
        screeningStatus: (p.screening_status as RoomScreeningStatus) || null,
        error: '',
      };
    case 'participant.joined':
    case 'participant.updated': {
      const participant = p.participant as Participant;
      const screening = { ...state.screening };
      delete screening[participant.id];
      return {
        ...state,
        screening,
        room: state.room
          ? {
              ...state.room,
              participants: [
                ...state.room.participants.filter((x) => x.id !== participant.id),
                participant,
              ],
            }
          : null,
      };
    }
    case 'participant.left': {
      const screening = { ...state.screening };
      delete screening[p.participant_id as string];
      return {
        ...state,
        screening,
        room: state.room
          ? {
              ...state.room,
              participants: state.room.participants.filter((x) => x.id !== p.participant_id),
            }
          : null,
      };
    }
    case 'transcript.final': {
      const turn = p.turn as Turn;
      return {
        ...state,
        turns: state.turns.some((t) => t.id === turn.id)
          ? state.turns.map((t) => (t.id === turn.id ? turn : t))
          : [...state.turns, turn],
      };
    }
    case 'translation.ready':
      return {
        ...state,
        turns: state.turns.map((t) =>
          t.id === p.utterance_id
            ? {
                ...t,
                translations: {
                  ...t.translations,
                  [p.target_language as string]: p.text as string,
                },
              }
            : t,
        ),
      };
    case 'pipeline.status':
      return { ...state, stages: { ...state.stages, [p.speaker_id as string]: p.stage as string } };
    case 'screening.updated':
      if (!state.room?.participants.some((member) => member.id === p.speaker_id)) return state;
      return { ...state, screening: { ...state.screening, [p.speaker_id as string]: p as unknown as RoomScreeningSample } };
    case 'metrics.updated':
      return { ...state, metrics: p as unknown as Metrics };
    case 'confirmation.updated':
      return {
        ...state,
        turns: state.turns.map((t) =>
          t.id === p.utterance_id ? { ...t, confirmed_by: p.confirmed_by as string[] } : t,
        ),
      };
    case 'pipeline.error':
      return { ...state, error: p.message as string };
    case 'error.dismiss':
      return { ...state, error: '' };
    case 'demo.complete':
      return { ...state, demoComplete: true };
    default:
      return state;
  }
}
