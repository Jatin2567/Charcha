import { expect, it } from 'vitest';
import { makeDemoTurn } from './demo';
import { confirmationText, canConfirm, understanding, turnRecovery } from './turnUnderstanding';
import { recapText, recapPrintHtml, whatsappRecap } from './recapExport';
import type { Recap, Turn } from '../types/domain';

const turn: Turn = { ...makeDemoTurn(0), speaker_id: 'speaker', text: 'कल दस बजे मिलते हैं।',
  translations: { ta: 'நாளை பத்து மணிக்கு சந்திப்போம்.' }, listeners_recorded: true,
  listeners: { a: 'Asha', b: 'Ravi' }, confirmed_by: ['a'], status: 'complete' };
const recap = { room: { title: 'Meeting notes', code: 'abcdef123456', mode: 'live', participants: [] },
  turns: [turn], ended_at: '2026-11-08T10:00:00Z', localDemo: false } as unknown as Recap;

it('does not turn one acknowledgement into agreement by everyone', () => {
  expect(understanding(turn).all).toBe(false);
  expect(confirmationText(turn)).toContain('Ravi: not yet confirmed');
  expect(confirmationText(turn)).toContain('Asha: confirmed understanding');
  expect(understanding({...turn, confirmed_by:['a','b']}).all).toBe(true);
  expect(understanding({...turn, confirmed_by:['a','b'], superseded_by:'new'}).all).toBe(false);
  expect(canConfirm(turn,'speaker')).toBe(false);
  expect(canConfirm(turn,'late')).toBe(false);
  expect(canConfirm(turn,'b')).toBe(true);
});
it('keeps legacy listener eligibility and empty rooms explicit', () => {
  expect(understanding({...turn, listeners: {}, listeners_recorded: false}).all).toBe(false);
  expect(confirmationText({...turn, listeners: {}, listeners_recorded: false})).toContain('Listener list not recorded');
  expect(understanding({...turn, listeners:{}, confirmed_by:[]}).all).toBe(false);
  expect(confirmationText({...turn, listeners:{}, confirmed_by:[]})).toContain('No other listeners');
});
it('preserves both scripts, missing translations and individual confirmations in exports', () => {
  for(const output of [recapText(recap,'ta'),recapPrintHtml(recap,'ta'),whatsappRecap(recap,'ta')]) {
    expect(output).toContain(turn.text);
    expect(output).toContain(turn.translations.ta);
    expect(output).toContain('Ravi: not yet confirmed');
    expect(output).toContain('not agreement');
  }
  expect(recapText(recap,'bn')).toContain('[Translation unavailable]');
  expect(recapText({...recap,localDemo:true},'ta')).toContain('SCRIPTED DEMONSTRATION');
});
it('escapes all user content in the printable document', () => {
  const payload = '</p><img src=x onerror=alert(1)><script>alert(1)</script>';
  const hostile = { ...recap, room:{...recap.room,title:payload}, turns:[{...turn,text:payload,speaker_name:payload,listeners:{a:payload},translations:{ta:payload}}] };
  const html = recapPrintHtml(hostile,'ta',payload);
  expect(html).not.toContain('<script>');
  expect(html).not.toContain('<img');
  expect(html).toContain('&lt;script&gt;');
});
it('keeps failed delivery visible without claiming a successful retry', () => {
  const failed = {...turn,status:'error' as const,recovery_reason:'queue_expired' as const};
  expect(turnRecovery(failed)?.detail).toContain('not delivered completely');
  expect(recapText({...recap,turns:[failed]},'ta')).toContain('repeat the missed phrase');
  expect(turnRecovery({...turn,status:'error'})?.detail).toContain('No automatic retry');
  expect(turnRecovery(turn)).toBeNull();
});
