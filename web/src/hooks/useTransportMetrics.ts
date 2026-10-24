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
    if (!roomCode || !participantId || typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel(transportChannel(roomCode, participantId));
    channel.onmessage = ({ data }) => {
      if (isTransportMetrics(data) && Math.abs(Date.now() - Date.parse(data.measured_at)) < 15000)
        setMetrics(data);
    };
    channel.postMessage({ type: 'request' });
    const timer = setInterval(() => {
      setMetrics((current) =>
        current && Date.now() - Date.parse(current.measured_at) > 15000 ? null : current,
      );
    }, 3000);
    return () => {
      clearInterval(timer);
      channel.close();
    };
  }, [roomCode, participantId]);
  return metrics;
}
