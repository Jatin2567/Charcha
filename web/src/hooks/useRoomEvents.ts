import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { initialRoomState, roomReducer } from '../state/roomReducer';
import type { Membership } from '../types/domain';
import { websocketUrl, startServerDemo } from '../services/api';
import { demoEvent, makeDemoTurn, SCRIPTED_TURNS } from '../services/demo';
export function useRoomEvents(m: Membership) {
  const [state, dispatch] = useReducer(roomReducer, { ...initialRoomState, room: m.room });
  const [connection, setConnection] = useState(m.localDemo ? 'Local demonstration' : 'Connecting…');
  const [running, setRunning] = useState(false);
  const [retry, setRetry] = useState(0);
  const timer = useRef<number | undefined>(undefined);
  const socket = useRef<WebSocket | null>(null);
  useEffect(() => {
    if (m.localDemo) {
      setConnection('Local demonstration');
      return;
    }
    let disposed = false;
    const ws = new WebSocket(websocketUrl(m.room.code), [
      'artha-events',
      `artha-token.${m.session_token}`,
    ]);
    socket.current = ws;
    ws.onopen = () => {
      if (!disposed) setConnection('Connected');
    };
    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        dispatch(event);
        if (event.type === 'demo.complete' || event.type === 'room.snapshot') setRunning(false);
      } catch {
        setConnection('Received an invalid event. Reconnect to recover.');
      }
    };
    ws.onerror = () => setConnection('Connection interrupted');
    ws.onclose = () => {
      if (!disposed) setConnection('Disconnected');
    };
    return () => {
      disposed = true;
      ws.close();
    };
  }, [m.localDemo, m.room.code, m.session_token, retry]);
  useEffect(() => () => clearInterval(timer.current), []);
  const startDemo = useCallback(async () => {
    if (running) return;
    setRunning(true);
    if (!m.localDemo) {
      try {
        await startServerDemo(m);
      } catch (e) {
        setRunning(false);
        throw e;
      }
      return;
    }
    let index = 0;
    const next = () => {
      if (index >= SCRIPTED_TURNS.length) {
        clearInterval(timer.current);
        setRunning(false);
        dispatch(demoEvent('demo.complete', {}));
        return;
      }
      const turn = makeDemoTurn(index++);
      dispatch(demoEvent('transcript.final', { turn }));
    };
    next();
    timer.current = window.setInterval(next, 4600);
  }, [m, running]);
  return {
    state,
    dispatch,
    connection,
    running,
    startDemo,
    reconnect: () => setRetry((x) => x + 1),
  };
}
