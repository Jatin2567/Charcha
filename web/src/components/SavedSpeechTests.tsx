import { hindiTamilProviderReport } from '../services/hindiTamilProviderEvidence';
import { tamilHindiFollowupReport } from '../services/tamilHindiFollowupEvidence';
import { HindiTamilProviderEvidence } from './HindiTamilProviderEvidence';
import { TamilHindiFollowupEvidence } from './TamilHindiFollowupEvidence';
import './SavedSpeechTests.css';

/** Historical controlled-flow evidence; deliberately independent of the current usage ledger. */
export function SavedSpeechTests() {
  const original = hindiTamilProviderReport();
  const followup = tamilHindiFollowupReport();
  if (original === null && followup === null) return null;
  return (
    <section className="saved-speech-tests" aria-labelledby="saved-speech-tests-title">
      <div>
        <h2 id="saved-speech-tests-title">Saved speech tests</h2>
        <p>
          Saved controlled-flow reservations are separate historical records. They do not add to the
          current local session totals or establish a provider invoice. Local audio testing keeps
          its isolated ledger; account balances and Modal charges are not inferred here.
        </p>
      </div>
      <HindiTamilProviderEvidence evidence={original} />
      <TamilHindiFollowupEvidence evidence={followup} />
    </section>
  );
}
