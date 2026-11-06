import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { MeetingCaptions } from './MeetingCaptions';
import { makeDemoTurn } from '../services/demo';
import { recapText } from '../pages/Recap';
import type { Recap } from '../types/domain';

it('shows precisely which listeners still need to acknowledge a correction', () => {
  const original = makeDemoTurn(0);
  const correction = {
    ...original,
    id: 'new',
    replaces_id: original.id,
    listeners: { a: 'Asha', b: 'Ravi' },
    confirmed_by: ['a'],
  };
  const html = renderToStaticMarkup(
    createElement(MeetingCaptions, {
      turns: [{ ...original, superseded_by: 'new' }, correction],
      language: 'hi',
      selfId: 'b',
      demo: false,
      emptyMessage: '',
      large: false,
      onResize: () => {},
      announce: true,
    }),
  );
  expect(html).toContain('Earlier version');
  expect(html).toContain('Waiting for Ravi');
  expect(html).not.toContain('Waiting for Asha');
});

it('exports the old wording but counts acknowledgements only on current messages', () => {
  const original = makeDemoTurn(0);
  const turns = [
    { ...original, superseded_by: 'new', confirmed_by: ['a'] },
    { ...original, id: 'new', replaces_id: original.id, confirmed_by: [] },
  ];
  const recap = {
    room: { title: 'Plans', code: '123456', mode: 'demo' },
    ended_at: '2026-11-04',
    turns,
  } as Recap;
  const result = recapText(recap, 'hi');
  expect(result).toContain('Messages with a recorded acknowledgement: 0/1');
  expect(result).toContain('Earlier version · replaced');
  expect(result).toContain('Corrected message');
});
