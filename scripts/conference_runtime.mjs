/** Pure launch configuration; importing this module starts no process or network request. */
import { readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';

export function launchOptions(args) {
  const option = (name) => {
    const at = args.indexOf(name);
    if (at < 0) return undefined;
    const value = args[at + 1];
    if (!value || value.startsWith('--') || args.indexOf(name, at + 1) >= 0)
      throw new Error('A launch option is missing or repeated.');
    return value;
  };
  const mode = args.includes('--live') ? 'live' : 'transport';
  if (args.includes('--screening-monitor') && args.includes('--screening-enforce'))
    throw new Error('Choose one screening mode.');
  const screening = args.includes('--screening-monitor') ? 'monitor' : args.includes('--screening-enforce') ? 'enforce' : 'off';
  if (mode === 'live' && args.includes('--verify'))
    throw new Error('Provider-free RTC verification cannot run in live mode.');
  return { mode, screening, plan: args.includes('--plan'), check: args.includes('--check'),
    privateClient: option('--evon-client-file'), evonBase: option('--evon-base-url'),
    evonModel: option('--evon-model') };
}

export function privateEvonOverrides(file, endpoint, model) {
  if (!file) return {};
  if (!endpoint || !model || !model.trim())
    throw new Error('Private Evon configuration requires an explicit endpoint and model.');
  let url;
  try { url = new URL(endpoint); } catch { throw new Error('Use an HTTPS Modal endpoint for this private client.'); }
  if (url.protocol !== 'https:' || !url.hostname.endsWith('.modal.run') ||
      url.hostname === '.modal.run' || (url.port && url.port !== '443') ||
      url.username || url.password || url.search || url.hash || !/^\/v1\/?$/.test(url.pathname))
    throw new Error('Use an HTTPS Modal /v1 endpoint for this private client.');
  let data;
  try {
    if (statSync(file).size > 16384) throw new Error();
    data = JSON.parse(readFileSync(file, 'utf8'));
  } catch { throw new Error('The private Evon client file is missing or invalid; values are withheld.'); }
  if (!data || typeof data !== 'object' || Array.isArray(data) ||
      Object.keys(data).sort().join(',') !== 'api_key,modal_key,modal_secret' ||
      Object.values(data).some((value) => typeof value !== 'string' || !/^[!-~]{1,4096}$/.test(value)))
    throw new Error('The private Evon client must contain exactly three complete authentication values.');
  return { EVON_BASE_URL: endpoint.replace(/\/$/, ''), EVON_MODEL: model,
    EVON_API_KEY: data.api_key, EVON_MODAL_KEY: data.modal_key, EVON_MODAL_SECRET: data.modal_secret };
}

export function apiEnvironment(base, root, webPort, options, privateOverrides = {}) {
  const live = options.mode === 'live';
  const environment = { ...base, ...privateOverrides,
    ARTHA_MODE: options.mode, LIVEKIT_URL: 'ws://127.0.0.1:7880',
    LIVEKIT_INTERNAL_URL: 'ws://127.0.0.1:7880', LIVEKIT_API_KEY: 'devkey', LIVEKIT_API_SECRET: 'secret',
    AUDIO_SCREENING_MODE: options.screening || 'off', LOCAL_AUDIO_LAB_ENABLED: live ? 'false' : 'true',
    USAGE_REQUIRE_FLOW_APPROVAL: 'true', USAGE_SHOW_PRIVATE_BALANCE: 'false',
    USAGE_STT_MAX_RETRIES: '0', USAGE_VOICE_ENROLLMENTS_PER_DAY: '0',
    CORS_ORIGINS: `http://127.0.0.1:${webPort},http://localhost:${webPort}`,
    VITE_API_BASE_URL: '/api', VITE_DEMO_MODE: 'false' };
  if (options.evonBase) environment.EVON_BASE_URL = options.evonBase;
  if (options.evonModel) environment.EVON_MODEL = options.evonModel;
  if (!live) {
    Object.assign(environment, { GNANI_API_KEY: '', EVON_BASE_URL: '', EVON_MODEL: '', EVON_API_KEY: '',
      EVON_MODAL_KEY: '', EVON_MODAL_SECRET: '', USAGE_DB_PATH: resolve(root, 'work/local/transport-usage.sqlite3') });
  }
  for (const key of ['LIVEKIT_CONFIG', 'LIVEKIT_KEYS', 'LIVEKIT_KEY_FILE', 'NODE_IP', 'REDIS_HOST', 'REDIS_PASSWORD'])
    delete environment[key];
  return environment;
}

export function webEnvironment(base, apiPort) {
  const environment = { ...base, VITE_API_BASE_URL: '/api', VITE_DEMO_MODE: 'false',
    ARTHA_API_TARGET: `http://127.0.0.1:${apiPort}` };
  for (const key of Object.keys(environment))
    if (/^(?:GNANI_|EVON_|LIVEKIT_|TIMBRE_|VOICE_CLONE_|VITE_(?:GNANI|EVON|LIVEKIT|TIMBRE|VOICE_CLONE))/.test(key))
      delete environment[key];
  return environment;
}

export function launchPlan(options, webPort = 5180) {
  return { mode: options.mode, plan_only: true, starts_processes: false, starts_cloud_resources: false,
    reads_secrets: false, provider_calls: 0, web_port: webPort,
    translation: options.mode === 'live' ? 'Requires configuration and a separately approved operator flow.' : 'Disabled; original audio only.',
    livekit: 'Self-hosted loopback development server', microphone: 'Off on join; explicit user action required.',
    camera: 'Off on join; explicit user action required.', screening: options.screening || 'off', voice_cloning: 'deferred',
    provider_verification: 'Configuration presence is separate from provider connectivity and language acceptance.' };
}
