import { useCallback, useEffect, useState } from 'react';
import { fetchUsage, referenceUsage } from '../services/usage';
import type { UsageReport } from '../types/usage';

export function useUsage(localDemo: boolean, waiting: boolean) {
  const [report, setReport] = useState<UsageReport>(() => referenceUsage());
  const [available, setAvailable] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [visible, setVisible] = useState(() => document.visibilityState !== 'hidden');
  const [revision, setRevision] = useState(0);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    const change = () => setVisible(document.visibilityState !== 'hidden');
    document.addEventListener('visibilitychange', change);
    return () => document.removeEventListener('visibilitychange', change);
  }, []);
  useEffect(() => {
    if (waiting || !visible) {
      setLoading(false);
      return;
    }
    if (localDemo) {
      setReport(referenceUsage(new Date(), true));
      setAvailable(false);
      setError('');
      setLoading(false);
      setUpdatedAt(null);
      return;
    }
    let alive = true;
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    let deadline: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;
    const load = async () => {
      controller = new AbortController();
      deadline = setTimeout(() => controller?.abort(), 12000);
      setLoading(true);
      try {
        const next = await fetchUsage(controller.signal);
        if (!alive) return;
        setReport(next);
        setAvailable(true);
        setUpdatedAt(new Date());
        setError('');
      } catch (reason) {
        if (!alive) return;
        setReport(referenceUsage());
        setAvailable(false);
        setUpdatedAt(null);
        setError(
          reason instanceof Error && reason.name !== 'AbortError'
            ? reason.message
            : 'Usage summary timed out. Consumption is unknown until the service reconnects.',
        );
      } finally {
        clearTimeout(deadline);
        if (alive) {
          setLoading(false);
          if (autoRefresh) refreshTimer = setTimeout(() => void load(), 10000);
        }
      }
    };
    void load();
    return () => {
      alive = false;
      clearTimeout(refreshTimer);
      clearTimeout(deadline);
      controller?.abort();
    };
  }, [localDemo, waiting, visible, autoRefresh, revision]);

  return {
    report,
    available,
    error,
    loading,
    autoRefresh,
    setAutoRefresh,
    visible,
    refresh,
    updatedAt,
  };
}
