import { useCallback, useEffect, useState } from 'react';
import type { Membership } from '../types/domain';
import type { PerformanceReport, ReadinessReport } from '../types/performance';
import {
  emptyPerformance,
  fetchPerformance,
  fetchReadiness,
  referenceReadiness,
} from '../services/performance';

export function usePerformance(
  membership: Membership | null,
  localDemo: boolean,
  waiting: boolean,
) {
  const [report, setReport] = useState<PerformanceReport | null>(null);
  const [readiness, setReadiness] = useState<ReadinessReport>(referenceReadiness);
  const [readinessAvailable, setReadinessAvailable] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [visible, setVisible] = useState(() => document.visibilityState !== 'hidden');
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  const code = membership?.room.code;
  const token = membership?.session_token;
  const roomMode = membership?.room.mode;
  const scripted = localDemo || !!membership?.localDemo;

  useEffect(() => {
    const onVisibility = () => setVisible(document.visibilityState !== 'hidden');
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, []);
  useEffect(() => {
    setReport(null);
    setError('');
  }, [code, token]);
  useEffect(() => {
    if (waiting || !visible) return;
    if (scripted) {
      setReport(code ? emptyPerformance(code, 'demo') : null);
      setReadiness(referenceReadiness());
      setReadinessAvailable(false);
      setLoading(false);
      setError('');
      return;
    }
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;
    const load = async () => {
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), 12000);
      setLoading(true);
      const results = await Promise.allSettled([
        fetchReadiness(controller.signal),
        code && token ? fetchPerformance(code, token, controller.signal) : Promise.resolve(null),
      ]);
      clearTimeout(timeout);
      if (!alive) return;
      const [setup, measurements] = results;
      if (
        setup.status === 'fulfilled' &&
        Array.isArray(setup.value.requirements) &&
        Array.isArray(setup.value.deployment_checks)
      ) {
        setReadiness(setup.value);
        setReadinessAvailable(true);
      } else {
        setReadiness(referenceReadiness());
        setReadinessAvailable(false);
      }
      if (measurements.status === 'fulfilled') {
        if (
          measurements.value &&
          (!Array.isArray(measurements.value.samples) || !measurements.value.measurement)
        ) {
          setError(
            'This workspace service does not provide the performance report yet. Update the server and refresh.',
          );
        } else {
          setReport(measurements.value);
          setError('');
        }
      } else {
        setError(
          measurements.reason instanceof Error && measurements.reason.name !== 'AbortError'
            ? measurements.reason.message
            : 'The workspace service took too long to respond. Previously collected samples remain visible.',
        );
      }
      setLoading(false);
      if (autoRefresh) timer = setTimeout(() => void load(), 5000);
    };
    void load();
    return () => {
      alive = false;
      clearTimeout(timer);
      controller?.abort();
    };
  }, [code, token, roomMode, scripted, waiting, visible, autoRefresh, revision]);

  return {
    report,
    readiness,
    readinessAvailable,
    error,
    loading,
    autoRefresh,
    setAutoRefresh,
    refresh,
    visible,
  };
}
