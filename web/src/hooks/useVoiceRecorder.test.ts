import { describe, expect, it } from 'vitest';
import { encodeWav } from './useVoiceRecorder';
describe('voice enrollment PCM encoder', () => {
  it('produces mono 16-bit PCM WAV with correct frame count and sample rate', async () => {
    const blob = encodeWav(new Float32Array([0, 0.5, -0.5, 1, -1]), 16000);
    const view = new DataView(await blob.arrayBuffer());
    const ascii = (start: number, length: number) =>
      String.fromCharCode(...new Uint8Array(view.buffer, start, length));
    expect(blob.type).toBe('audio/wav');
    expect(ascii(0, 4)).toBe('RIFF');
    expect(ascii(8, 4)).toBe('WAVE');
    expect(view.getUint16(20, true)).toBe(1);
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getUint32(40, true)).toBe(10);
    expect(view.getInt16(50, true)).toBe(32767);
    expect(view.getInt16(52, true)).toBe(-32768);
  });
  it('clips out-of-range samples before PCM conversion', async () => {
    const view = new DataView(await encodeWav(new Float32Array([2, -2]), 24000).arrayBuffer());
    expect(view.getInt16(44, true)).toBe(32767);
    expect(view.getInt16(46, true)).toBe(-32768);
  });
});
