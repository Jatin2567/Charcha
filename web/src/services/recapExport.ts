import { languageName, type Language, type Recap } from '../types/domain';
import { confirmationText, turnRecovery } from './turnUnderstanding';

const note = 'Confirmations record understanding, not agreement or proof of accuracy. Missing translations and confirmations remain unknown.';
const fingerprintNote = 'The SHA-256 fingerprint identifies the saved source record. It is not a signature, certification or hash of this PDF file.';
const date = (value: string) => new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) + ' IST';
const demo = (recap: Recap) => recap.localDemo || recap.room.mode === 'demo';
const version = (turn: Recap['turns'][number]) => turn.superseded_by ? 'Earlier version · replaced' : turn.replaces_id ? 'Corrected message' : 'Message';

export function recapText(recap: Recap, language: Language, hash?: string): string {
  const current = recap.turns.filter(t => !t.superseded_by);
  const acknowledged = current.filter(t => t.confirmed_by.length > 0).length;
  return [
    'CHARCHA · BILINGUAL CONVERSATION RECORD', recap.room.title,
    demo(recap) ? 'SCRIPTED DEMONSTRATION — example content' : 'Participant conversation record',
    `Room: ${recap.room.code} | Ended: ${date(recap.ended_at)}`,
    `Original wording + ${languageName(language)} translation`,
    `Messages with a recorded acknowledgement: ${acknowledged}/${current.length}. This is not unanimous confirmation.`,
    note, '',
    ...recap.turns.map((turn, i) => [
      `${i + 1}. ${turn.speaker_name} · ${version(turn)} · ${turn.status}`,
      `${languageName(turn.source_language)} (original): ${turn.text}`,
      `${languageName(language)}: ${turn.source_language === language ? turn.text : turn.translations[language] || '[Translation unavailable]'}`,
      confirmationText(turn, recap.room.participants),
      turnRecovery(turn)?.detail || '',
    ].filter(Boolean).join('\n') + '\n'),
    hash ? `Source record SHA-256: ${hash}` : 'Source record SHA-256: unavailable', fingerprintNote,
  ].join('\n');
}

export function whatsappRecap(recap: Recap, language: Language, hash?: string) {
  return '*Charcha · Conversation recap*\n\n' + recapText(recap, language, hash);
}

const escape = (value: string) => value.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));

export function recapPrintHtml(recap: Recap, language: Language, hash?: string) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(recap.room.title)} — Charcha</title><style>
    @page { size:A4; margin:16mm; } * { box-sizing:border-box; } body { max-width:900px; margin:24px auto; padding:0 16px; color:#24272e; background:#fff; font:14px/1.65 Arial,"Nirmala UI",sans-serif; }
    h1 { font-size:26px; line-height:1.3; } h2 { font-size:16px; margin:0 0 8px; } h3 { font-size:12px; color:#365bd6; margin:0; } p { margin:5px 0 12px; white-space:pre-wrap; overflow-wrap:anywhere; }
    header { border-bottom:3px solid #365bd6; padding-bottom:16px; } article { padding:18px 0; border-bottom:1px solid #d6dbe4; } .bilingual { display:grid; grid-template-columns:1fr 1fr; gap:20px; } .confirmation { font-size:12px; } .note { font-size:12px; color:#535e70; } .warning { color:#815111; } footer { margin-top:24px; } .hash { font-size:11px; overflow-wrap:anywhere; }
    @media print { body { margin:0; padding:0; max-width:none; } article { break-inside:avoid; } h2,h3 { break-after:avoid; } p { orphans:3; widows:3; } .bilingual { display:block; } }
    @media(max-width:600px) { .bilingual { grid-template-columns:1fr; } }
    </style></head><body><header><strong>CHARCHA · CONVERSATION RECORD</strong><h1>${escape(recap.room.title)}</h1><p>${escape(recap.room.code)} · ${escape(date(recap.ended_at))}</p>${demo(recap) ? '<p class="warning">SCRIPTED DEMONSTRATION — example content</p>' : ''}<p class="note">${note}</p></header>
    ${recap.turns.map((turn, i) => `<article><h2>${i+1}. ${escape(turn.speaker_name)} · ${version(turn)}</h2><p class="note">Status: ${escape(turn.status)}</p><div class="bilingual"><div><h3>${escape(languageName(turn.source_language))} · Original</h3><p dir="auto" lang="${escape(turn.source_language)}">${escape(turn.text)}</p></div><div><h3>${escape(languageName(language))} · ${turn.source_language === language ? 'Same language' : 'Translation'}</h3><p dir="auto" lang="${escape(language)}">${escape(turn.source_language === language ? turn.text : turn.translations[language] || '[Translation unavailable]')}</p></div></div><p class="confirmation">${escape(confirmationText(turn, recap.room.participants))}</p>${turnRecovery(turn) ? `<p class="warning">${escape(turnRecovery(turn)!.detail)}</p>` : ''}</article>`).join('')}
    <footer><p class="hash">Source record SHA-256: ${escape(hash || 'unavailable')}</p><p class="note">${fingerprintNote}</p><p class="note">Includes participant names and conversation content. Share intentionally.</p></footer></body></html>`;
}

export function printRecap(recap: Recap, language: Language, hash?: string) {
  const popup = window.open('', '_blank');
  if (!popup) throw new Error('Allow pop-ups for Charcha, then choose Save PDF / Print again. You can still download the text recap.');
  popup.opener = null;
  popup.document.write(recapPrintHtml(recap, language, hash));
  popup.document.close();
  void popup.document.fonts.ready.then(() => {
    if (!popup.closed) { popup.focus(); popup.print(); }
  });
}
