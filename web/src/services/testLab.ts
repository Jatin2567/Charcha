import { TEST_SCENARIOS, TEST_STAGES } from '../data/testLab';
import type { TestStageId } from '../data/testLab';

export const TEST_LAB_STORAGE_KEY = 'charcha.test-lab.v1';
export type TestOutcome = 'pending' | 'pass' | 'fail' | 'blocked';
export interface TestObservation {
  stage: TestStageId;
  scenario: string;
  outcome: TestOutcome;
  observed_at: string;
  pipeline_ms: number | null;
  listener_ms: number | null;
  notes: string;
}
export interface TestLabStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}
export function browserTestStorage(): TestLabStorage | null {
  try {
    return globalThis.localStorage || null;
  } catch {
    return null;
  }
}
const outcomes: TestOutcome[] = ['pending', 'pass', 'fail', 'blocked'];
const plainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
export const observationKey = (stage: TestStageId, scenario: string) => `${stage}:${scenario}`;
export const safeTestNotes = (text: string) =>
  text
    .replace(/vach_[A-Za-z0-9_-]+/gi, '[redacted key]')
    .replace(/Bearer\s+[^\s]+/gi, '[redacted token]')
    .replace(/\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/g, '[redacted token]')
    .slice(0, 400);
export function latencyValue(value: string): number | null {
  if (!value.trim()) return null;
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0 || number > 3600000)
    throw new Error('Enter a delay from 0 to 3,600,000 milliseconds, or leave it empty.');
  return number;
}
/** Whitelist observations only; never load/export arbitrary browser or room state. */
export function cleanObservations(value: unknown): Record<string, TestObservation> {
  if (!plainObject(value)) return {};
  const result: Record<string, TestObservation> = {};
  for (const stage of TEST_STAGES) {
    for (const scenario of TEST_SCENARIOS.filter((entry) => entry.stages.includes(stage.id))) {
      const key = observationKey(stage.id, scenario.id);
      if (!Object.hasOwn(value, key)) continue;
      const item = value[key];
      if (
        !plainObject(item) ||
        !outcomes.includes(item.outcome as TestOutcome) ||
        typeof item.observed_at !== 'string' ||
        !Number.isFinite(Date.parse(item.observed_at)) ||
        typeof item.notes !== 'string'
      )
        continue;
      const validLatency = (entry: unknown): entry is number | null =>
        entry === null ||
        (typeof entry === 'number' && Number.isFinite(entry) && entry >= 0 && entry <= 3600000);
      if (!validLatency(item.pipeline_ms) || !validLatency(item.listener_ms)) continue;
      const notes = safeTestNotes(item.notes);
      if (item.listener_ms !== null && !notes.trim()) continue;
      result[key] = {
        stage: stage.id,
        scenario: scenario.id,
        outcome: item.outcome as TestOutcome,
        observed_at: new Date(item.observed_at).toISOString(),
        pipeline_ms: stage.mode === 'transport' ? null : item.pipeline_ms,
        listener_ms: item.listener_ms,
        notes,
      };
    }
  }
  return result;
}
export function loadObservations(
  storage: Pick<TestLabStorage, 'getItem'> | null,
): Record<string, TestObservation> {
  try {
    return cleanObservations(JSON.parse(storage?.getItem(TEST_LAB_STORAGE_KEY) || '{}'));
  } catch {
    return {};
  }
}
export function saveObservations(
  storage: Pick<TestLabStorage, 'setItem'> | null,
  observations: Record<string, TestObservation>,
) {
  if (!storage)
    throw new Error(
      'Browser storage is unavailable. Enable it to save observations on this browser.',
    );
  storage.setItem(TEST_LAB_STORAGE_KEY, JSON.stringify(cleanObservations(observations)));
}
export function clearObservation(
  storage: Pick<TestLabStorage, 'setItem'> | null,
  observations: Record<string, TestObservation>,
  stage: TestStageId,
  scenario: string,
) {
  const next = cleanObservations(observations);
  delete next[observationKey(stage, scenario)];
  saveObservations(storage, next);
  return next;
}
export function testLabReport(observations: Record<string, TestObservation>, now = new Date()) {
  const entries = Object.values(cleanObservations(observations));
  return {
    schema_version: 1,
    record_type: 'manual_test_observations',
    generated_at: now.toISOString(),
    evidence:
      'Human-entered observations; no automatic pass, provider verification or latency benchmark is asserted.',
    latency_boundary: {
      pipeline_ms:
        'Manually copied server queue-to-first-PCM plus STT proxy; not listener playback.',
      listener_ms:
        'Manually observed external speech-end-to-listener playback delay; method must be described in notes.',
    },
    observations: entries,
  };
}
