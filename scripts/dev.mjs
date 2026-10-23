import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { createServer } from 'node:net';

const root = fileURLToPath(new URL('../', import.meta.url));
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
start('uv', [
  'run',
  '--project',
  'server',
  'uvicorn',
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
]);
const vite = [
  join(root, 'node_modules/vite/bin/vite.js'),
  join(root, 'web/node_modules/vite/bin/vite.js'),
].find(existsSync);
if (!vite) {
  console.error('Install frontend dependencies first: npm install');
  stop(1);
} else
  start(process.execPath, [vite, '--host', '127.0.0.1', 'web'], {
    ...process.env,
    ARTHA_API_TARGET: `http://127.0.0.1:${apiPort}`,
  });
