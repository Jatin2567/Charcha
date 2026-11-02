import { useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import type { AudioSession } from '../services/livekit';

/** Tap existing browser tracks. The analysis graph has no connection to a speaker. */
export function CallWaveforms({ session }: { session: RefObject<AudioSession | null> }) {
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState('');
  const mic = useRef<HTMLCanvasElement>(null);
  const receiver = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!enabled) return;
    let ctx: AudioContext;
    try {
      ctx = new AudioContext();
    } catch {
      setError('Waveform display is unavailable in this browser.');
      return;
    }
    let active = true;
    const micAnalyser = ctx.createAnalyser();
    const receivedAnalyser = ctx.createAnalyser();
    const gain = ctx.createGain();
    gain.connect(receivedAnalyser);
    const sources = new Map<MediaStreamTrack, MediaStreamAudioSourceNode>();
    const data = new Uint8Array(256);
    const palette = getComputedStyle(document.documentElement);
    const micColor = palette.getPropertyValue('--ink').trim();
    const receivedColor = palette.getPropertyValue('--accent').trim();
    micAnalyser.fftSize = receivedAnalyser.fftSize = data.length;
    const paint = (canvas: HTMLCanvasElement | null, analyser: AnalyserNode, color: string) => {
      const graph = canvas?.getContext('2d');
      if (!canvas || !graph) return;
      analyser.getByteTimeDomainData(data);
      graph.clearRect(0, 0, canvas.width, canvas.height);
      graph.strokeStyle = color;
      graph.lineWidth = 2;
      graph.beginPath();
      data.forEach((amplitude, i) => {
        const x = (i * canvas.width) / (data.length - 1);
        const y = (amplitude / 255) * canvas.height;
        if (i === 0) graph.moveTo(x, y);
        else graph.lineTo(x, y);
      });
      graph.stroke();
    };
    const draw = () => {
      const inputs = session.current?.waveformSources();
      const tracks = new Set(inputs?.received);
      if (inputs?.microphone) tracks.add(inputs.microphone);
      for (const [track, node] of sources) {
        if (!tracks.has(track)) {
          node.disconnect();
          sources.delete(track);
        }
      }
      for (const track of tracks) {
        if (sources.has(track) || track.readyState === 'ended') continue;
        const node = ctx.createMediaStreamSource(new MediaStream([track]));
        node.connect(track === inputs?.microphone ? micAnalyser : gain);
        sources.set(track, node);
      }
      gain.gain.value = inputs?.gain ?? 1;
      paint(mic.current, micAnalyser, micColor);
      paint(receiver.current, receivedAnalyser, receivedColor);
    };
    const timer = window.setInterval(draw, 100);
    void ctx.resume().catch(() => {
      if (active) setError('The browser paused waveform analysis. Close and reopen the display.');
    });
    return () => {
      active = false;
      clearInterval(timer);
      sources.forEach((node) => node.disconnect());
      gain.disconnect();
      micAnalyser.disconnect();
      receivedAnalyser.disconnect();
      void ctx.close().catch(() => {});
    };
  }, [enabled, session]);
  return (
    <div className="call-waveforms">
      <button
        className="button secondary full"
        aria-expanded={enabled}
        onClick={() => {
          setError('');
          setEnabled(!enabled);
        }}
      >
        {enabled ? 'Hide live waveforms' : 'Show live waveforms'}
      </button>
      {enabled && (
        <>
          <p>
            <strong>Your microphone</strong>
            <canvas ref={mic} width={256} height={40} aria-label="Microphone waveform" />
          </p>
          <p>
            <strong>Incoming conversation</strong>
            <canvas ref={receiver} width={256} height={40} aria-label="Received audio waveform" />
          </p>
          {error && <small role="status">{error}</small>}
        </>
      )}
    </div>
  );
}
