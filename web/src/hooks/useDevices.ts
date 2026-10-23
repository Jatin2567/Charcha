import { useCallback, useEffect, useRef, useState } from 'react';

export function useDevices() {
  const [inputs, setInputs] = useState<MediaDeviceInfo[]>([]);
  const [outputs, setOutputs] = useState<MediaDeviceInfo[]>([]);
  const [error, setError] = useState('');
  const [level, setLevel] = useState(0);
  const [enabled, setEnabled] = useState(false);
  const [pending, setPending] = useState(false);
  const stream = useRef<MediaStream | null>(null);
  const context = useRef<AudioContext | null>(null);
  const frame = useRef(0);
  const generation = useRef(0);
  const alive = useRef(true);
  const requesting = useRef(false);
  const refresh = useCallback(async () => {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      if (!alive.current) return;
      setInputs(devices.filter((d) => d.kind === 'audioinput'));
      setOutputs(devices.filter((d) => d.kind === 'audiooutput'));
    } catch {
      if (alive.current)
        setError('Audio devices are unavailable in this browser. Use HTTPS or localhost.');
    }
  }, []);
  const release = useCallback(() => {
    generation.current++;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    cancelAnimationFrame(frame.current);
    void context.current?.close();
    context.current = null;
  }, []);
  const stop = useCallback(() => {
    release();
    if (alive.current) {
      setEnabled(false);
      setLevel(0);
    }
  }, [release]);
  const start = async (device = 'default'): Promise<boolean> => {
    if (requesting.current) return false;
    stop();
    requesting.current = true;
    setPending(true);
    const requestGeneration = generation.current;
    try {
      if (!navigator.mediaDevices)
        throw new Error('Microphone access requires HTTPS or localhost.');
      const media = await navigator.mediaDevices.getUserMedia({
        audio: {
          deviceId: device === 'default' ? undefined : { exact: device },
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      if (!alive.current || requestGeneration !== generation.current) {
        media.getTracks().forEach((t) => t.stop());
        return false;
      }
      stream.current = media;
      const ctx = new AudioContext();
      context.current = ctx;
      const source = ctx.createMediaStreamSource(media);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        if (!alive.current || requestGeneration !== generation.current) return;
        analyser.getByteTimeDomainData(data);
        const rms = Math.sqrt(
          data.reduce((sum, v) => sum + ((v - 128) / 128) ** 2, 0) / data.length,
        );
        setLevel(Math.min(1, rms * 5));
        frame.current = requestAnimationFrame(tick);
      };
      tick();
      setEnabled(true);
      setError('');
      await refresh();
      return true;
    } catch (e) {
      release();
      if (alive.current) {
        setEnabled(false);
        setError(e instanceof Error ? e.message : 'Microphone permission was denied.');
      }
      return false;
    } finally {
      requesting.current = false;
      if (alive.current) setPending(false);
    }
  };
  useEffect(() => {
    alive.current = true;
    void refresh();
    navigator.mediaDevices?.addEventListener('devicechange', refresh);
    return () => {
      alive.current = false;
      release();
      navigator.mediaDevices?.removeEventListener('devicechange', refresh);
    };
  }, [refresh, release]);
  return { inputs, outputs, error, level, enabled, pending, start, stop, refresh };
}
export async function playTestTone(output = 'default') {
  const ctx = new AudioContext();
  try {
    if (output !== 'default' && 'setSinkId' in ctx)
      await (ctx as AudioContext & { setSinkId: (id: string) => Promise<void> }).setSinkId(output);
    const oscillator = ctx.createOscillator();
    const gain = ctx.createGain();
    oscillator.type = 'sine';
    oscillator.frequency.value = 523.25;
    gain.gain.setValueAtTime(0, ctx.currentTime);
    gain.gain.linearRampToValueAtTime(0.12, ctx.currentTime + 0.05);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.7);
    oscillator.connect(gain);
    gain.connect(ctx.destination);
    oscillator.start();
    oscillator.stop(ctx.currentTime + 0.75);
    oscillator.onended = () => void ctx.close();
  } catch (e) {
    await ctx.close();
    throw e;
  }
}
