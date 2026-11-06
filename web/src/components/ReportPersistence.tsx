import type { PersistenceStatus } from '../types/performance';

export function ReportPersistence({ status }: { status?: PersistenceStatus }) {
  if (!status) return null;
  if (status.state === 'saved' && !status.last_saved_at) return null;
  const problem = status.state === 'retrying' || status.state === 'unavailable';
  return <div className={`notice ${problem ? 'warning' : 'info'}`} role="status">
    <span><strong>{problem ? 'Report saving needs attention.' : status.state === 'pending' ? 'Saving your report…' : 'Report saved.'}</strong>{' '}
      {problem ? 'The call can continue. Unsaved readings remain in memory while saving retries; they could be lost if the server stops.'
        : status.state === 'pending' ? 'The latest readings are waiting to be stored.' : 'Your measurements are stored for this account.'}
      {status.last_saved_at && <> Last saved {new Date(status.last_saved_at).toLocaleString()}.</>}
    </span>
  </div>;
}
