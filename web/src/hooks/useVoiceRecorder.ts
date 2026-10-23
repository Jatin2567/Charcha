import { useCallback, useEffect, useRef, useState } from 'react';

export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };
  text(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, 'WAVE');
  text(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((sample, i) =>
    view.setInt16(
      44 + i * 2,
      Math.max(-1, Math.min(1, sample)) * (sample < 0 ? 32768 : 32767),
      true,
    ),
  );
  return new Blob([buffer], { type: 'audio/wav' });
}

export function useVoiceRecorder() {
  const [recording, setRecording] = useState(false);
  const [pending, setPending] = useState(false);
  const [duration, setDuration] = useState(0);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const context = useRef<AudioContext | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const processor = useRef<ScriptProcessorNode | null>(null);
  const samples = useRef<Float32Array[]>([]);
  const timer = useRef<number | undefined>(undefined);
  const started = useRef(0);
  const stopRef = useRef<() => void>(() => {});
  const alive = useRef(true);
  const generation = useRef(0);
  const requesting = useRef(false);
  const isRecording = useRef(false);

  const release = useCallback(() => {
    generation.current++;
    clearInterval(timer.current);
    processor.current?.disconnect();
    if (processor.current) processor.current.onaudioprocess = null;
    processor.current = null;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    void context.current?.close().catch(() => {});
    context.current = null;
    isRecording.current = false;
  }, []);

  const stop = () => {
    const ctx = context.current;
    if (ctx && alive.current) {
      const size = Math.min(
        samples.current.reduce((count, chunk) => count + chunk.length, 0),
        ctx.sampleRate * 30,
      );
      const joined = new Float32Array(size);
      let offset = 0;
      for (const chunk of samples.current) {
        const part = chunk.subarray(0, size - offset);
        joined.set(part, offset);
        offset += part.length;
        if (offset === size) break;
      }
      setBlob(encodeWav(joined, ctx.sampleRate));
      setDuration(size / ctx.sampleRate);
    }
    release();
    samples.current = [];
    if (alive.current) setRecording(false);
  };
  stopRef.current = stop;

  const start = async (device = 'default') => {
    if (requesting.current || isRecording.current || !alive.current) return;
    release();
    const requestGeneration = generation.current;
    requesting.current = true;
    setPending(true);
    setError('');
    setBlob(null);
    setDuration(0);
    samples.current = [];
    try {
      if (!navigator.mediaDevices)
        throw new Error('Microphone access requires HTTPS or localhost.');
      const media = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          deviceId: device === 'default' ? undefined : { exact: device },
        },
      });
      if (!alive.current || requestGeneration !== generation.current) {
        media.getTracks().forEach((track) => track.stop());
        return;
      }
      stream.current = media;
      const ctx = new AudioContext();
      context.current = ctx;
      await ctx.resume();
      if (!alive.current || requestGeneration !== generation.current) return;
      const source = ctx.createMediaStreamSource(media);
      const node = ctx.createScriptProcessor(4096, 1, 1);
      processor.current = node;
      node.onaudioprocess = (event) => {
        if (alive.current && requestGeneration === generation.current)
          samples.current.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      };
      source.connect(node);
      const silent = ctx.createGain();
      silent.gain.value = 0;
      node.connect(silent);
      silent.connect(ctx.destination);
      isRecording.current = true;
      setRecording(true);
      started.current = Date.now();
      timer.current = window.setInterval(() => {
        const elapsed = (Date.now() - started.current) / 1000;
        if (alive.current) setDuration(elapsed);
        if (elapsed >= 29.8) stopRef.current();
      }, 100);
    } catch (failure) {
      release();
      if (alive.current) {
        setRecording(false);
        setError((failure as Error).message);
      }
    } finally {
      requesting.current = false;
      if (alive.current) setPending(false);
    }
  };

  const clear = () => {
    release();
    samples.current = [];
    setRecording(false);
    setBlob(null);
    setDuration(0);
    setError('');
  };
  const loadFile = async (file: File) => {
    if (requesting.current || isRecording.current) return;
    release();
    const requestGeneration = generation.current;
    let ctx: AudioContext | null = null;
    try {
      setError('');
      if (file.size > 10 * 1024 * 1024) throw new Error('Use a WAV file smaller than 10 MB.');
      const data = await file.arrayBuffer();
      if (!alive.current || requestGeneration !== generation.current) return;
      ctx = new AudioContext();
      const decoded = await ctx.decodeAudioData(data.slice(0));
      if (!alive.current || requestGeneration !== generation.current) return;
      if (decoded.duration < 5 || decoded.duration > 30)
        throw new Error('Your reference must contain between 5 and 30 seconds of speech.');
      const mono = new Float32Array(decoded.length);
      for (let channel = 0; channel < decoded.numberOfChannels; channel++) {
        const values = decoded.getChannelData(channel);
        for (let i = 0; i < values.length; i++) mono[i] += values[i] / decoded.numberOfChannels;
      }
      setBlob(encodeWav(mono, decoded.sampleRate));
      setDuration(decoded.duration);
    } catch (failure) {
      if (alive.current) setError((failure as Error).message);
    } finally {
      await ctx?.close().catch(() => {});
    }
  };

  useEffect(() => {
    if (!blob) {
      setUrl('');
      return;
    }
    const value = URL.createObjectURL(blob);
    setUrl(value);
    return () => URL.revokeObjectURL(value);
  }, [blob]);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      release();
      samples.current = [];
    };
  }, [release]);
  return { recording, pending, duration, blob, url, error, start, stop, clear, loadFile };
}
