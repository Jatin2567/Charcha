import type { invitationScope } from '../services/invitation';
import './InvitationHelp.css';

export function InvitationHelp({ scope }: { scope: ReturnType<typeof invitationScope> }) {
  return (
    <section className="invitation-help" aria-label="Invitation reach">
      <strong>{scope.title}</strong>
      <p>{scope.detail}</p>
      <a href="#/tests?stage=device-check" target="_blank" rel="noreferrer">
        Two-device setup &amp; free checklist ↗
      </a>
    </section>
  );
}
