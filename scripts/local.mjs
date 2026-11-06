// Local conference stack. HTTP/API stay on loopback; RTC uses local interfaces.
// Original-audio mode clears provider credentials; live mode retains flow approval.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, openSync, closeSync } from 'node:fs';
import { createServer } from 'node:net';
import { createSocket } from 'node:dgram';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { launchOptions, apiEnvironment, webEnvironment, privateEvonOverrides, launchPlan } from './conference_runtime.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
let options;
try { options = launchOptions(process.argv.slice(2)); }
catch (error) { console.error(error.message); process.exit(1); }
const python = join(
  root,
  'server/.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
);
const livekit =
  process.env.LIVEKIT_BINARY ||
  join(root, 'work/bin', process.platform === 'win32' ? 'livekit-server.exe' : 'livekit-server');
const vite = [
  join(root, 'node_modules/vite/bin/vite.js'),
  join(root, 'web/node_modules/vite/bin/vite.js'),
].find(existsSync);
const rtcOnly = process.argv.includes('--verify');
const webPort = Number((process.env.CHARCHA_WEB_PORT ?? process.env.ARTHA_WEB_PORT) || 5180);
if (!Number.isInteger(webPort) || webPort < 1 || webPort > 65535 || [7880, 7881].includes(webPort)) {
  console.error('CHARCHA_WEB_PORT must be a valid port distinct from the local media ports.');
  process.exit(1);
}
if (options.plan) {
  console.log(JSON.stringify(launchPlan(options, webPort), null, 2));
  process.exit(0);
}
let privateOverrides;
try { privateOverrides = options.mode === 'live' ? privateEvonOverrides(options.privateClient, options.evonBase, options.evonModel) : {}; }
catch (error) { console.error(error.message); process.exit(1); }
const children = [];
let stopping = false;
const delay = (ms) => new Promise((done) => setTimeout(done, ms));

async function freePort(port) {
  if (!Number.isInteger(port) || port < 1 || port > 65535) return false;
  return new Promise((done) => {
    const server = createServer();
    server.once('error', () => done(false));
    server.listen(port, '127.0.0.1', () => server.close(() => done(true)));
  });
}
async function freeUdp(port) {
  return new Promise((done) => {
    const socket = createSocket('udp4');
    socket.once('error', () => {
      socket.close();
      done(false);
    });
    socket.bind(port, '127.0.0.1', () => socket.close(() => done(true)));
  });
}
async function waitFor(url, accept, child) {
  for (let count = 0; count < 60 && !stopping && child.exitCode === null; count++) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(500) });
      if (response.ok && (await accept(response))) return true;
    } catch {
      /* this owned service is starting */
    }
    await delay(150);
  }
  return false;
}
function launch(command, args, env, stdio = 'inherit') {
  const child = spawn(command, args, { cwd: root, env, stdio, windowsHide: true });
  children.push(child);
  child.on('error', (error) => {
    console.error(error.message);
    stop(1);
  });
  child.on('exit', (code) => {
    if (!stopping && !rtcOnly) stop(code || 0);
  });
  return child;
}
async function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of [...children].reverse()) {
    if (child.exitCode !== null || child.signalCode !== null) continue;
    if (process.platform === 'win32' && Number.isInteger(child.pid)) {
      // Only PIDs returned by this launcher's own spawn calls; never kill by name.
      spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore', windowsHide: true });
    } else child.kill('SIGTERM');
  }
  await delay(250);
  process.exit(code);
}
process.on('SIGINT', () => {
  void stop();
});
process.on('SIGTERM', () => {
  void stop();
});

for (const [path, instruction] of [
  [python, 'Run scripts/setup.ps1 first.'],
  [livekit, 'Run scripts/setup-livekit.ps1 or set LIVEKIT_BINARY.'],
]) {
  if (!existsSync(path)) {
    console.error(instruction);
    process.exit(1);
  }
}
if (!rtcOnly && !vite) {
  console.error('Install frontend dependencies first.');
  process.exit(1);
}
const environment = apiEnvironment(process.env, root, webPort, options, privateOverrides);
const configuration = spawnSync(python, ['scripts/check_conference_config.py', '--mode', options.mode],
  { cwd: root, env: environment, encoding: 'utf8', windowsHide: true });
if (configuration.status !== 0) {
  console.error(configuration.stdout?.trim() || 'Local configuration could not be checked; no services started.');
  process.exit(1);
}
if (options.check) {
  console.log(configuration.stdout.trim());
  console.log('Local dependencies and configuration checked. No services, provider calls or cloud resources started.');
  process.exit(0);
}
for (const port of [7880, 7881, ...(rtcOnly ? [] : [webPort])]) {
  if (!(await freePort(port))) {
    console.error(
      `Local port ${port} is occupied. Stop only your earlier Charcha test, or choose a different CHARCHA_WEB_PORT.`,
    );
    process.exit(1);
  }
}
if (!(await freeUdp(7882))) {
  console.error(
    'Local UDP port 7882 is occupied. Stop your earlier local media test before restarting.',
  );
  process.exit(1);
}
mkdirSync(join(root, 'work/local'), { recursive: true });
const logFile = join(root, 'work/local/livekit.log');
const log = openSync(logFile, 'a');
// Let LiveKit advertise the real local interfaces rather than rewriting every
// media address to 127.0.0.1. Include loopback as an additional candidate, not
// the only one, and resolve browser mDNS names without changing Chrome privacy.
const rtcConfig =
  'rtc:\n  use_mdns: true\n  enable_loopback_candidate: true\nlogging:\n  level: warn\n';
const rtcServer = launch(
  livekit,
  ['--dev', '--bind', '127.0.0.1', '--udp-port', '7882', '--config-body', rtcConfig],
  environment,
  ['ignore', log, log],
);
closeSync(log);
const ready = await waitFor('http://127.0.0.1:7880', async () => true, rtcServer);
if (!ready) {
  console.error(`Local LiveKit did not start. Inspect ${logFile}`);
  await stop(1);
}

if (rtcOnly) {
  console.log('Local RTC verification: synthetic PCM, no microphone and no vendor requests.');
  for (const script of ['verify_transport.py', 'verify_routing.py', 'verify_same_language.py']) {
    const child = launch(python, ['-u', join('scripts', script)], environment);
    const code = await new Promise((done) => child.once('exit', done));
    if (code !== 0) await stop(code || 1);
  }
  await stop();
} else {
  let apiPort;
  for (const port of (process.env.CHARCHA_API_PORT ?? process.env.ARTHA_API_PORT)
    ? [Number((process.env.CHARCHA_API_PORT ?? process.env.ARTHA_API_PORT))]
    : [8000, 8100, 8200]) {
    if (port === webPort) continue;
    if (await freePort(port)) {
      apiPort = port;
      break;
    }
  }
  if (!apiPort) {
    console.error('No free API port. Set CHARCHA_API_PORT to a free local port.');
    await stop(1);
  }
  const api = launch(
    python,
    [
      '-m',
      'uvicorn',
      'charcha.main:app',
      '--app-dir',
      'server',
      '--host',
      '127.0.0.1',
      '--port',
      String(apiPort),
      '--no-access-log',
      '--log-level',
      'warning',
    ],
    environment,
  );
  if (
    !(await waitFor(
      `http://127.0.0.1:${apiPort}/api/health`,
      async (response) => (await response.json()).mode === options.mode,
      api,
    ))
  ) {
    console.error('The local call API did not become ready in the selected mode.');
    await stop(1);
  }
  launch(
    process.execPath,
    [vite, '--host', '127.0.0.1', '--port', String(webPort), '--strictPort', 'web'],
    webEnvironment(process.env, apiPort),
  );
  console.log(`\nLocal audio: http://127.0.0.1:${webPort}/#/tests`);
  console.log(`Local API: http://127.0.0.1:${apiPort} · local media: ws://127.0.0.1:7880`);
  console.log(
    'Create a room and open its invite in another browser profile. Use headphones; microphones start off.',
  );
  console.log(
    options.mode === 'live'
      ? 'Live translation is configured. Paid interpretation stays locked until an operator approves a bounded flow. Ctrl+C stops this owned stack.'
      : 'Raw microphone audio only. Translation, captions and cloning are disabled. Ctrl+C stops this owned stack.',
  );
  console.log(
    `Experimental screening: ${environment.AUDIO_SCREENING_MODE}. Audio lab: http://127.0.0.1:${webPort}/#/audio-lab`,
  );
}
