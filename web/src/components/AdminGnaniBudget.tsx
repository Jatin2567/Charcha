import { useEffect, useState } from 'react';
import { request } from '../services/api';

type Budget = { host_email: string; limit_inr: number; reserved_inr: number; remaining_inr: number; revision: number; managed: boolean };
const rupees = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 4 });

export function AdminGnaniBudget() {
  const [budget, setBudget] = useState<Budget | null>(null);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState('');
  const [managed, setManaged] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    void request<{ budget: Budget | null }>('/admin/gnani-budget').then(({ budget }) => {
      if (active) { setBudget(budget); setDraft(budget ? String(budget.limit_inr) : ''); setManaged(budget?.managed ?? false); }
    }).catch((e: Error) => { if (active) { setBudget(null); setMessage(e.message); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refresh]);
  return (
    <section aria-labelledby="gnani-budget-title">
      <h2 id="gnani-budget-title">Speech billing controls</h2>
      {loading ? <p>Loading allowance…</p> : budget ? <>
        <p>Meetings created by <strong>{budget.host_email}</strong> can interpret every supported language without operator approval.</p>
        {!budget.managed && <p><strong>Owner monitors Gnani billing.</strong> Charcha records service activity, but does not calculate a balance or impose a speech-credit ceiling.</p>}
        {budget.managed && <dl className="conference-setup-grid">
          <div><dt>Total limit</dt><dd>{rupees.format(budget.limit_inr)}</dd></div>
          <div><dt>Estimated usage</dt><dd>{rupees.format(budget.reserved_inr)}</dd></div>
          <div><dt>Available</dt><dd>{rupees.format(budget.remaining_inr)}</dd></div>
        </dl>}
        <form onSubmit={async (event) => {
          event.preventDefault();
          setSaving(true);
          try {
            const result = await request<{ budget: Budget }>('/admin/gnani-budget', {
              method: 'POST', body: JSON.stringify({ limit_inr: Number(draft), revision: budget.revision, managed }),
            });
            setBudget(result.budget); setDraft(String(result.budget.limit_inr));
            setMessage('Billing controls updated for current and future meetings.');
          } catch (e) { setMessage((e as Error).message); } finally { setSaving(false); }
        }}>
          <label className="check-line"><input type="checkbox" checked={managed} onChange={(e) => setManaged(e.target.checked)} />Enforce a locally estimated speech budget</label>
          {managed && <label>Total limit in rupees<input type="number" min="0" max="1000000" step="1" required
            value={draft} onChange={(e) => setDraft(e.target.value)} /></label>}
          <button className="button primary" disabled={saving || draft === '' || (Number(draft) === budget.limit_inr && managed === budget.managed)}>Save billing controls</button>
        </form>
        {managed && <p>Set ₹0 to pause speech usage. The estimate covers standard STT/TTS only; enabling this control blocks new voice enrollment because cloning rates are not configured. Past monetary usage is incomplete for periods monitored by the owner. Use Gnani’s dashboard for actual charges.</p>}
      </> : <p>Automatic meeting funding is unavailable on this server.</p>}
      <button type="button" className="text-link" disabled={loading || saving}
        onClick={() => { setMessage(''); setRefresh((n) => n + 1); }}>Refresh allowance</button>
      <p role="status">{message}</p>
    </section>
  );
}
