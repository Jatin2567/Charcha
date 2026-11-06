import { useEffect, useState } from 'react';
import { isTransportMetrics, transportChannel } from '../services/transportMetrics';
import type { TransportMetrics } from '../services/transportMetrics';

export function useTransportMetrics(
  roomCode?: string,
  participantId?: string,
): TransportMetrics | null {
  const [metrics, setMetrics] = useState<TransportMetrics | null>(null);
  useEffect(() => {
    setMetrics(null);
    if (!roomCode || !participantId) return;
    const topic = transportChannel(roomCode, participantId);
    const receive = (data: unknown) => {
      if (isTransportMetrics(data) && Math.abs(Date.now() - Date.parse(data.measured_at)) < 15000)
        setMetrics(data);
    };
    const local = (event: Event) => receive((event as CustomEvent).detail);
    window.addEventListener(topic, local);
    window.dispatchEvent(new Event(topic + '.request'));
    const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(topic);
    if (channel) {
      channel.onmessage = ({ data }) => receive(data);
      channel.postMessage({ type: 'request' });
    }
    const timer = setInterval(() => {
      setMetrics((current) =>
        current && Date.now() - Date.parse(current.measured_at) > 15000 ? null : current,
      );
    }, 3000);
    return () => {
      clearInterval(timer);
      window.removeEventListener(topic, local);
      channel?.close();
    };
  }, [roomCode, participantId]);
  return metrics;
}
