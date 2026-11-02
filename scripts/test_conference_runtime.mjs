import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, unlinkSync, rmdirSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { apiEnvironment, webEnvironment, launchOptions, privateEvonOverrides, launchPlan } from './conference_runtime.mjs';

test('provider-free mode defeats inherited credentials and unsafe flow preferences', () => {
  const env = apiEnvironment({ GNANI_API_KEY: 'private-fixture', EVON_BASE_URL: 'https://remote.invalid',
    EVON_MODEL: 'private-model', EVON_MODAL_KEY: 'proxy-fixture', EVON_MODAL_SECRET: 'proxy-secret',
    AUDIO_SCREENING_MODE: 'enforce', USAGE_REQUIRE_FLOW_APPROVAL: 'false' }, process.cwd(), 5180,
    launchOptions([]));
  for (const key of ['GNANI_API_KEY', 'EVON_BASE_URL', 'EVON_MODEL', 'EVON_API_KEY', 'EVON_MODAL_KEY', 'EVON_MODAL_SECRET'])
    assert.equal(env[key], '');
  assert.equal(env.USAGE_REQUIRE_FLOW_APPROVAL, 'true');
  assert.equal(env.AUDIO_SCREENING_MODE, 'off');
  assert.equal(env.ARTHA_MODE, 'transport');
  assert.match(env.USAGE_DB_PATH, /transport-usage\.sqlite3$/);
});

test('live calls require operator approval and do not inherit automatic retries or cloning', () => {
  const env = apiEnvironment({ GNANI_API_KEY: 'fixture', USAGE_STT_MAX_RETRIES: '8',
    USAGE_VOICE_ENROLLMENTS_PER_DAY: '8', LIVEKIT_CONFIG: 'unrelated-daemon' }, process.cwd(), 5180,
    launchOptions(['--live', '--evon-base-url', 'http://127.0.0.1:8001/v1', '--evon-model', 'owned-model']));
  assert.equal(env.ARTHA_MODE, 'live');
  assert.equal(env.GNANI_API_KEY, 'fixture');
  assert.equal(env.USAGE_STT_MAX_RETRIES, '0');
  assert.equal(env.USAGE_VOICE_ENROLLMENTS_PER_DAY, '0');
  assert.equal(env.USAGE_SHOW_PRIVATE_BALANCE, 'false');
  assert.equal(env.LIVEKIT_CONFIG, undefined);
  assert.equal(env.EVON_MODEL, 'owned-model');
});

test('frontend dev process receives no provider authentication or inherited remote API target', () => {
  const env = webEnvironment({ GNANI_API_KEY: 'private', EVON_API_KEY: 'private', LIVEKIT_API_SECRET: 'private',
    VITE_EVON_API_KEY: 'private', VITE_API_BASE_URL: 'https://unrelated.invalid', PATH: 'retained' }, 8100);
  assert.equal(env.PATH, 'retained');
  assert.equal(env.VITE_API_BASE_URL, '/api');
  assert.equal(env.ARTHA_API_TARGET, 'http://127.0.0.1:8100');
  assert.equal(Object.values(env).includes('private'), false);
});

test('private Modal credentials are scoped to an explicit approved-shaped origin', () => {
  const directory = mkdtempSync(join(tmpdir(), 'artha-config-test-'));
  const file = join(directory, 'private.json');
  try {
    writeFileSync(file, JSON.stringify({ api_key: 'inference-fixture', modal_key: 'proxy-fixture', modal_secret: 'secret-fixture' }));
    const env = privateEvonOverrides(file, 'https://owned-app.modal.run/v1', 'owned-model');
    assert.equal(env.EVON_API_KEY, 'inference-fixture');
    for (const destination of ['http://owned-app.modal.run/v1', 'https://elsewhere.invalid/v1',
      'https://owned-app.modal.run/v1?secret=value', 'https://user@owned-app.modal.run/v1'])
      assert.throws(() => privateEvonOverrides(file, destination, 'owned-model'));
    writeFileSync(file, JSON.stringify({ api_key: 'must-not-print\nsecret', modal_key: 'fixture', modal_secret: 'fixture' }));
    assert.throws(() => privateEvonOverrides(file, 'https://owned-app.modal.run/v1', 'owned-model'),
      (error) => !error.message.includes('must-not-print'));
  } finally {
    if (existsSync(file)) unlinkSync(file);
    rmdirSync(directory);
  }
});

test('planning never opens a supplied private file or starts the local stack', () => {
  const result = spawnSync(process.execPath, ['scripts/local.mjs', '--live', '--plan',
    '--evon-client-file', 'does-not-exist-private.json'], { encoding: 'utf8' });
  assert.equal(result.status, 0);
  const plan = JSON.parse(result.stdout);
  assert.equal(plan.starts_processes, false);
  assert.equal(plan.reads_secrets, false);
  assert.equal(plan.provider_calls, 0);
  assert.equal(plan.mode, 'live');
});

test('ambiguous modes or missing private configuration arguments fail safely', () => {
  assert.throws(() => launchOptions(['--screening-monitor', '--screening-enforce']));
  assert.throws(() => launchOptions(['--live', '--verify']));
  assert.throws(() => launchOptions(['--evon-client-file']));
  assert.throws(() => privateEvonOverrides('fixture.json', undefined, 'model'));
});

test('VoiceShield explicitly enables local monitoring while provider access stays disabled', () => {
  const options = launchOptions(['--screening-monitor']);
  const env = apiEnvironment({ GNANI_API_KEY: 'fixture', EVON_API_KEY: 'fixture', AUDIO_SCREENING_MODE: 'enforce' }, process.cwd(), 5180, options);
  assert.equal(env.ARTHA_MODE, 'transport');
  assert.equal(env.AUDIO_SCREENING_MODE, 'monitor');
  assert.equal(env.GNANI_API_KEY, '');
  assert.equal(env.EVON_API_KEY, '');
  assert.equal(launchPlan(options).screening, 'monitor');
});
