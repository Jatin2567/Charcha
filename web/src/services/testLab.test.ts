import { describe, expect, it } from 'vitest';
import {
  TEST_LAB_STORAGE_KEY,
  browserTestStorage,
  cleanObservations,
  clearObservation,
  latencyValue,
  loadObservations,
  observationKey,
  saveObservations,
  testLabReport,
} from './testLab';
import type { TestLabStorage, TestObservation } from './testLab';
import { TEST_SCENARIOS } from '../data/testLab';

const observation = (patch: Partial<TestObservation> = {}): TestObservation => ({
  stage: 'interpretation',
  scenario: 'negation',
  outcome: 'pass',
  observed_at: '2026-10-27T10:00:00Z',
  pipeline_ms: 550,
  listener_ms: null,
  notes: 'Hindi to Tamil: blue requested, red rejected.',
  ...patch,
});
function memoryStorage(): TestLabStorage {
  const entries = new Map<string, string>();
  return {
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => {
      entries.set(key, value);
    },
  };
}
const negationKey = observationKey('interpretation', 'negation');

describe('manual Test lab observations', () => {
  it('keeps each of the 20 listener reviews independent from the reverse direction', () => {
    const directions = TEST_SCENARIOS.filter((entry) => entry.stages.includes('five-language'));
    expect(new Set(directions.map((entry) => entry.id)).size).toBe(20);
    expect(
      directions.every((entry) => entry.script[0].length > 10 && entry.expected.length > 0),
    ).toBe(true);
    const storage = memoryStorage();
    const entry = observation({
      stage: 'five-language',
      scenario: 'review-hi-ta',
      notes: 'Listener repeated ten.',
    });
    const key = observationKey(entry.stage, entry.scenario);
    saveObservations(storage, { [key]: entry });
    const loaded = loadObservations(storage);
    expect(loaded[key]?.notes).toBe('Listener repeated ten.');
    expect(loaded[observationKey('five-language', 'review-ta-hi')]).toBeUndefined();
  });
  it('accepts only finite bounded delays and keeps empty values unknown', () => {
    expect(latencyValue('')).toBeNull();
    expect(latencyValue('  ')).toBeNull();
    expect(latencyValue('0')).toBe(0);
    expect(latencyValue('625.5')).toBe(625.5);
    for (const value of ['-1', '3600001', 'Infinity', 'NaN', 'unknown'])
      expect(() => latencyValue(value)).toThrow('Enter a delay');
  });
  it('handles corrupt or unavailable browser storage without inventing results', () => {
    expect(loadObservations(null)).toEqual({});
    expect(loadObservations({ getItem: () => '{broken' })).toEqual({});
    expect(
      loadObservations({
        getItem: () => {
          throw new Error('Storage blocked');
        },
      }),
    ).toEqual({});
    expect(() => saveObservations(null, {})).toThrow('Browser storage is unavailable');
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      get() {
        throw new Error('Restricted');
      },
    });
    try {
      expect(browserTestStorage()).toBeNull();
    } finally {
      if (descriptor) Object.defineProperty(globalThis, 'localStorage', descriptor);
      else Reflect.deleteProperty(globalThis, 'localStorage');
    }
  });
  it('whitelists the current stage/scenario schema and strips arbitrary state', () => {
    const entry = observation();
    const result = cleanObservations({
      [negationKey]: {
        ...entry,
        session_token: 'private',
        audio: 'private',
        stage: 'cloning',
        scenario: 'invented',
      },
      'local-audio:negation': entry,
      'interpretation:invented': entry,
      arbitrary: { credentials: 'private' },
    });
    expect(Object.keys(result)).toEqual([negationKey]);
    expect(result[negationKey]).toEqual({ ...entry, observed_at: '2026-10-27T10:00:00.000Z' });
    expect(cleanObservations(Object.create({ [negationKey]: entry }))).toEqual({});
  });
  it('rejects malformed saved outcomes, timestamps, delays and missing timing method notes', () => {
    for (const patch of [
      { outcome: 'automatic-pass' },
      { observed_at: 'not-a-date' },
      { pipeline_ms: -1 },
      { listener_ms: Infinity },
      { pipeline_ms: '500' },
      { notes: null },
      { listener_ms: 500, notes: '   ' },
    ])
      expect(cleanObservations({ [negationKey]: { ...observation(), ...patch } })).toEqual({});
  });
  it('never exports an STT/MT/TTS pipeline delay for the raw-audio stage', () => {
    const key = observationKey('local-audio', 'greeting');
    const result = cleanObservations({ [key]: observation({ pipeline_ms: 900 }) });
    expect(result[key].pipeline_ms).toBeNull();
    expect(result[key].stage).toBe('local-audio');
    expect(result[key].scenario).toBe('greeting');
    const deviceKey = observationKey('device-check', 'device-sustained');
    const deviceResult = cleanObservations({
      [deviceKey]: observation({ pipeline_ms: 900, outcome: 'blocked' }),
    });
    expect(deviceResult[deviceKey].pipeline_ms).toBeNull();
    expect(deviceResult[deviceKey].outcome).toBe('blocked');
    expect(testLabReport(deviceResult).observations[0].stage).toBe('device-check');
  });
  it('round trips bounded notes and redacts recognizable keys and bearer/JWT tokens', () => {
    const storage = memoryStorage();
    const notes = 'vach_example-secret Bearer sample-private eyJabc.def.ghi ' + 'x'.repeat(500);
    saveObservations(storage, { [negationKey]: observation({ notes }) });
    expect(storage.getItem(TEST_LAB_STORAGE_KEY)).toBeTruthy();
    const entry = loadObservations(storage)[negationKey];
    expect(entry.notes).not.toContain('example-secret');
    expect(entry.notes).not.toContain('sample-private');
    expect(entry.notes).not.toContain('eyJabc.def.ghi');
    expect(entry.notes.length).toBeLessThanOrEqual(400);
  });
  it('clears one saved stage result without losing other stage observations', () => {
    const storage = memoryStorage();
    const secondKey = observationKey('second-device', 'negation');
    const entries = {
      [negationKey]: observation(),
      [secondKey]: observation({ stage: 'second-device', outcome: 'blocked' }),
    };
    const next = clearObservation(storage, entries, 'interpretation', 'negation');
    expect(Object.keys(next)).toEqual([secondKey]);
    expect(loadObservations(storage)).toEqual(next);
    expect(entries[negationKey]).toBeTruthy();
  });
  it('exports human-entered evidence with explicit latency boundaries and no application state', () => {
    const report = testLabReport(
      { [negationKey]: observation() },
      new Date('2026-10-27T11:00:00Z'),
    );
    expect(report.record_type).toBe('manual_test_observations');
    expect(report.evidence).toContain('no automatic pass');
    expect(report.latency_boundary.listener_ms).toContain('Manually observed');
    expect(report.generated_at).toBe('2026-10-27T11:00:00.000Z');
    expect(report.observations).toHaveLength(1);
    expect(report).not.toHaveProperty('room');
    expect(report).not.toHaveProperty('session_token');
  });
});
