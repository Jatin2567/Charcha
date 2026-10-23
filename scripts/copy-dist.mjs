import { cp, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const destination = fileURLToPath(new URL('../dist/', import.meta.url));
await mkdir(destination, { recursive: true });
await cp(new URL('../web/dist/', import.meta.url), destination, { recursive: true });
console.log('Frontend ready in dist/.');
