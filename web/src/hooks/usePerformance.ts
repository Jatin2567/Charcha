import { useCallback, useEffect, useState } from 'react';
import type { Membership } from '../types/domain';
import type { PerformanceReport, ReadinessReport, MeetingReportEntry, PersistenceStatus } from '../types/performance';
import {
  emptyPerformance,
  fetchPerformance,
  fetchCurrentCallPerformance,
  fetchReadiness,
  referenceReadiness,
  fetchPerformanceHistory,
  fetchSavedPerformance,
} from '../services/performance';

export function usePerformance(
  membership: Membership | null,
  localDemo: boolean,
  waiting: boolean,
  discoverCurrent = false,
  selectedReport = '',
) {
  const [report, setReport] = useState<PerformanceReport | null>(null);
  const [history, setHistory] = useState<MeetingReportEntry[]>([]);
  const [historyError, setHistoryError] = useState('');
  const [persistence, setPersistence] = useState<PersistenceStatus | undefined>();
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
  }, [code, token, selectedReport]);
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
      const signal = controller.signal;
      const setup = fetchReadiness(signal).then((value) => {
        if (alive && Array.isArray(value.requirements) && Array.isArray(value.deployment_checks)) {
          setReadiness(value);
          setReadinessAvailable(true);
        }
      }).catch(() => { if (alive) setReadinessAvailable(false); });
      const saved = discoverCurrent ? fetchPerformanceHistory(signal).then((value) => {
        if (alive) { setHistory(value.reports); setPersistence(value.persistence); setHistoryError(''); }
      }).catch(() => { if (alive) setHistoryError('Saved meeting list could not refresh. Try again.'); }) : Promise.resolve();
      const [measurements] = await Promise.allSettled([
        discoverCurrent ? (selectedReport ? fetchSavedPerformance(selectedReport, signal) : fetchCurrentCallPerformance(signal)) :
          code && token ? fetchPerformance(code, token, signal) : Promise.resolve(null),
      ]);
      if (!alive) { clearTimeout(timeout); return; }
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
      await Promise.all([setup, saved]);
      clearTimeout(timeout);
      if (alive && autoRefresh) timer = setTimeout(() => void load(), 5000);
    };
    void load();
    return () => {
      alive = false;
      clearTimeout(timer);
      controller?.abort();
    };
  }, [code, token, roomMode, scripted, waiting, visible, autoRefresh, revision, discoverCurrent, selectedReport]);

  return {
    report,
    history,
    historyError,
    persistence,
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
