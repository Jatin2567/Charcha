import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { createServer } from 'node:net';

const root = fileURLToPath(new URL('../', import.meta.url));
const providerChecks = process.argv.includes('--provider-checks');
const checksWebPort = Number(process.env.ARTHA_WEB_PORT || 5180);
if (providerChecks && (!Number.isInteger(checksWebPort) || checksWebPort < 1 || checksWebPort > 65535)) {
  console.error('ARTHA_WEB_PORT must be a valid local port.');
  process.exit(1);
}
const processes = [];
let stopping = false;
function start(command, args, env = process.env) {
  const process = spawn(command, args, { cwd: root, stdio: 'inherit', shell: false, env });
  processes.push(process);
  process.on('error', (error) => {
    console.error(`Unable to launch ${command}: ${error.message}`);
    stop(1);
  });
  process.on('exit', (code) => {
    if (!stopping) stop(code || 0);
  });
}
function stop(code) {
  if (stopping) return;
  stopping = true;
  for (const process of processes) process.kill('SIGTERM');
  setTimeout(() => process.exit(code), 350).unref();
}
process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
async function available(port) {
  return new Promise((resolve) => {
    const test = createServer();
    test.once('error', () => resolve(false));
    test.listen(port, '127.0.0.1', () => test.close(() => resolve(true)));
  });
}
let apiPort;
for (const candidate of process.env.ARTHA_API_PORT
  ? [Number(process.env.ARTHA_API_PORT)]
  : [8000, 8100, 8200]) {
  if (
    Number.isInteger(candidate) &&
    candidate > 0 &&
    candidate < 65536 &&
    (await available(candidate))
  ) {
    apiPort = candidate;
    break;
  }
}
if (!apiPort) {
  console.error('No API port is available. Set ARTHA_API_PORT to a free local port.');
  process.exit(1);
}
console.log(`Artha-Mesh API: http://127.0.0.1:${apiPort}`);
const serverEnvironment = providerChecks
  ? { ...process.env, ARTHA_MODE: 'live', USAGE_REQUIRE_FLOW_APPROVAL: 'true', USAGE_SHOW_PRIVATE_BALANCE: 'true',
      CORS_ORIGINS: `http://127.0.0.1:${checksWebPort},http://localhost:${checksWebPort}` }
  : process.env;
if (providerChecks) console.log('Local checks: open /#/usage. Paid provider flows remain locked until separately approved.');
const serverArguments = [
  'artha_mesh.main:app',
  '--app-dir',
  'server',
  '--host',
  '127.0.0.1',
  '--port',
  String(apiPort),
  '--reload',
  '--no-access-log',
  '--log-level',
  'warning',
];
if (providerChecks) {
  const installedPython = join(root, 'server/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  if (!existsSync(installedPython)) {
    console.error('Run the normal dependency setup first; local checks use the installed Python environment.');
    process.exit(1);
  }
  start(installedPython, ['-m', 'uvicorn', ...serverArguments], serverEnvironment);
} else {
  start('uv', ['run', '--project', 'server', 'uvicorn', ...serverArguments], serverEnvironment);
}
const vite = [
  join(root, 'node_modules/vite/bin/vite.js'),
  join(root, 'web/node_modules/vite/bin/vite.js'),
].find(existsSync);
if (!vite) {
  console.error('Install frontend dependencies first: npm install');
  stop(1);
} else
  start(process.execPath, [vite, '--host', '127.0.0.1',
    ...(providerChecks ? ['--port', String(checksWebPort), '--strictPort'] : []), 'web'], {
    ...process.env,
    ARTHA_API_TARGET: `http://127.0.0.1:${apiPort}`,
  });
