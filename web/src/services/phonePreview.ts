import { readLabWav } from './audioLab';
import { encodeWav } from '../hooks/useVoiceRecorder';

// Windowed bandpass rejects frequencies above the 8 kHz output's Nyquist limit.
// Coefficients use the 16 kHz source rate validated by readLabWav.
const radius = 32;
function lowPass(cutoff: number, offset: number) {
  return offset === 0
    ? (2 * cutoff) / 16000
    : Math.sin((2 * Math.PI * cutoff * offset) / 16000) / (Math.PI * offset);
}
const filter = Array.from({ length: 2 * radius + 1 }, (_, tap) => {
  const offset = tap - radius;
  const window = 0.54 + 0.46 * Math.cos((Math.PI * offset) / radius);
  return window * (lowPass(3400, offset) - lowPass(300, offset));
});

export function phonePreview(buffer: ArrayBuffer, addNoise: boolean) {
  const { dataStart, samples } = readLabWav(buffer);
  const input = new DataView(buffer, dataStart, samples * 2);
  const output = new Float32Array(Math.ceil(samples / 2));
  let seed = 271;
  for (let i = 0; i < output.length; i++) {
    const center = i * 2;
    let value = 0;
    for (let k = Math.max(-radius, -center); k <= Math.min(radius, samples - 1 - center); k++)
      value += (filter[k + radius] * input.getInt16(2 * (center + k), true)) / 32768;
    if (addNoise) {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      value += (seed / 4294967296 - 0.5) * 0.018;
    }
    output[i] = value;
  }
  return encodeWav(output, 8000);
}
