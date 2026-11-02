import { expect, it } from 'vitest';
import { encodeWav } from '../hooks/useVoiceRecorder';
import { phonePreview } from './phonePreview';

async function rendered(frequency: number, noise = false) {
  const samples = Float32Array.from(
    { length: 16000 },
    (_, i) => 0.4 * Math.sin((2 * Math.PI * frequency * i) / 16000),
  );
  const input = await encodeWav(samples, 16000).arrayBuffer();
  const file = await phonePreview(input, noise).arrayBuffer();
  const view = new DataView(file);
  expect(view.getUint32(24, true)).toBe(8000);
  expect(view.getUint32(40, true)).toBe(16000);
  let energy = 0;
  for (let i = 100; i < 7900; i++) energy += (view.getInt16(44 + i * 2, true) / 32768) ** 2;
  return Math.sqrt(energy / 7800);
}
it('retains speech-band audio, suppresses aliasing, and makes quiet noise optional and repeatable', async () => {
  expect(await rendered(1000)).toBeGreaterThan(0.25);
  expect(await rendered(5000)).toBeLessThan(0.002);
  expect(await rendered(0)).toBe(0);
  const noise = await rendered(0, true);
  expect(noise).toBeGreaterThan(0.003);
  expect(noise).toBeLessThan(0.008);
  expect(await rendered(0, true)).toBe(noise);
});
