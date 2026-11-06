import type { RoomScreeningSample, RoomScreeningStatus } from './localDiagnostics';
import type { Participant } from '../types/domain';

export function shieldingState(
  status: RoomScreeningStatus | null,
  connected: boolean,
  demo: boolean,
) {
  if (demo)
    return {
      label: 'Unavailable in demo',
      detail: 'Join a microphone room to analyze real audio.',
    };
  if (!connected)
    return {
      label: 'Updates paused',
      detail: 'Reconnect the room to receive current screening results.',
    };
  if (!status)
    return {
      label: 'Status unavailable',
      detail: 'The server has not reported its detector configuration.',
    };
  if (status.mode === 'off')
    return {
      label: 'Screening off',
      detail: 'The meeting server has microphone screening turned off.',
    };
  if (!status.model.ready)
    return {
      label: 'Detector unavailable',
      detail: 'The audio classifier could not load. No authenticity assessment is available.',
    };
  return status.mode === 'monitor'
    ? {
        label: 'Monitoring audio',
        detail:
          'The meeting server assesses original microphone audio as you speak. Flags appear below.',
      }
    : {
        label: 'Enforcement enabled',
        detail:
          'Audio is held until each window receives an assessment. Unknown and flagged windows are withheld.',
      };
}

export function screeningResultLabel(sample: RoomScreeningSample) {
  if (sample.mode === 'off') return 'Screening off';
  if (sample.status !== 'assessed') return 'Assessment unavailable';
  if (sample.verdict === 'suspicious') return 'Possible synthetic voice';
  if (sample.verdict === 'allow') return 'No flag';
  return 'Inconclusive';
}

export function hasVoiceFlag(sample: RoomScreeningSample) {
  return sample.mode !== 'off' && sample.status === 'assessed' && sample.verdict === 'suspicious';
}

export function activeScreeningSamples(
  samples: Record<string, RoomScreeningSample>,
  participants: Participant[],
  status: RoomScreeningStatus | null,
  connected: boolean,
) {
  if (!connected || !status?.model.ready || status.mode === 'off') return [];
  return participants
    .filter((person) => !person.muted && !person.is_agent && !person.is_demo)
    .map((person) => ({ person, sample: samples[person.id] }))
    .filter(
      (entry) =>
        entry.sample &&
        entry.sample.mode === status.mode &&
        entry.sample.speaker_id === entry.person.id,
    );
}

export function screeningMetric(value: number | null | undefined, unit = ' ms') {
  return value != null && Number.isFinite(value) && value >= 0
    ? `${Number(value.toFixed(unit === '' ? 6 : 2))}${unit}`
    : 'Not measured';
}

export function screeningReason(sample: RoomScreeningSample) {
  if (sample.status !== 'assessed') return 'The detector could not assess this window.';
  if (sample.reasons?.includes('insufficient_signal'))
    return 'Too little audible speech to assess this window.';
  if (sample.reasons?.includes('severe_clipping'))
    return 'Audio is distorted. Lower the microphone input level.';
  if (sample.reasons?.includes('model_inference_failed'))
    return 'Model inference failed. This result is inconclusive.';
  return sample.verdict === 'unknown'
    ? 'The model did not reach either decision threshold.'
    : 'An experimental acoustic assessment of one audio window.';
}
