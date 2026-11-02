export interface ColdStartDirection {
  route: string;
  capture_to_first_received_pcm_ms: number | null;
}
export interface ColdStartRun {
  run_id: string;
  passed: boolean | null;
  directions: ColdStartDirection[];
  mute_request_to_receiver_track_detached_ms: number | null;
  notes: string;
}
export interface ColdStartGroup {
  label: string;
  runs: ColdStartRun[];
}
export interface ColdStartEvidence {
  schema_version: 1;
  recorded_at: string | null;
  boundary: string;
  baseline: ColdStartGroup;
  after: ColdStartGroup;
  historical: ColdStartGroup | null;
  fix_summary: string[];
  limitations: string[];
}
const record = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
const text = (value: unknown, fallback = '') => (typeof value === 'string' ? value : fallback);
const array = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);
const duration = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null;

/** A deliberately small, public evidence contract: never export raw runtime objects. */
export function coldStartReport(value: unknown): ColdStartEvidence {
  const source = record(value);
  const group = (value: unknown, fallback: string): ColdStartGroup => {
    const source = record(value);
    return {
      label: text(source.label, fallback),
      runs: array(source.runs).map((value, index) => {
        const run = record(value);
        return {
          run_id: text(run.run_id, `run-${index + 1}`),
          passed: typeof run.passed === 'boolean' ? run.passed : null,
          directions: array(run.directions).map((value) => {
            const direction = record(value);
            return {
              route: text(direction.route, 'Unlabelled route'),
              capture_to_first_received_pcm_ms: duration(
                direction.capture_to_first_received_pcm_ms,
              ),
            };
          }),
          mute_request_to_receiver_track_detached_ms: duration(
            run.mute_request_to_receiver_track_detached_ms,
          ),
          notes: text(run.notes),
        };
      }),
    };
  };
  return {
    schema_version: 1,
    recorded_at: typeof source.recorded_at === 'string' ? source.recorded_at : null,
    boundary: text(source.boundary, 'Measurement boundary has not been recorded.'),
    baseline: group(source.baseline, 'Before the fix'),
    after: group(source.after, 'After the fix'),
    historical: source.historical && typeof source.historical === 'object' && !Array.isArray(source.historical)
      ? group(source.historical, 'Prior incident') : null,
    fix_summary: array(source.fix_summary).filter(
      (entry): entry is string => typeof entry === 'string',
    ),
    limitations: array(source.limitations).filter(
      (entry): entry is string => typeof entry === 'string',
    ),
  };
}

export function summarizeColdStarts(group: ColdStartGroup) {
  const values = group.runs
    .filter((run) => run.passed === true)
    .flatMap((run) => run.directions.map((row) => row.capture_to_first_received_pcm_ms))
    .filter((value): value is number => duration(value) !== null)
    .sort((a, b) => a - b);
  const middle = Math.floor(values.length / 2);
  const median = values.length
    ? values.length % 2
      ? values[middle]
      : (values[middle - 1] + values[middle]) / 2
    : null;
  return {
    sample_count: values.length,
    median_ms: median,
    min_ms: values[0] ?? null,
    max_ms: values.at(-1) ?? null,
    passed_runs: group.runs.filter((run) => run.passed === true).length,
    failed_runs: group.runs.filter((run) => run.passed === false).length,
    unrecorded_runs: group.runs.filter((run) => run.passed === null).length,
    run_count: group.runs.length,
  };
}

export function coldStartReduction(before: number | null, after: number | null): number | null {
  if (duration(before) === null || duration(after) === null) return null;
  return ((before! - after!) / before!) * 100;
}
