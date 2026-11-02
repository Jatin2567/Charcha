import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { demoEvent, makeDemoTurn } from '../services/demo';
import { initialRoomState, roomReducer } from '../state/roomReducer';
import type { Language, Turn } from '../types/domain';
import { MeetingCaptions } from './MeetingCaptions';

const render = (turns: Turn[], language: Language = 'ta') =>
  renderToStaticMarkup(
    createElement(MeetingCaptions, { turns, language, selfId: 'viewer', demo: false,
      emptyMessage: 'Waiting for speech', large: false, onResize: () => {}, announce: true }),
  );

describe('meeting captions', () => {
  it('retains overlapping speakers when an earlier translation arrives late', () => {
    const first: Turn = { ...makeDemoTurn(0), status: 'processing', translations: {} };
    const second = makeDemoTurn(1);
    let state = roomReducer(initialRoomState, demoEvent('transcript.final', { turn: first }));
    state = roomReducer(state, demoEvent('transcript.final', { turn: second }));
    expect(render(state.turns)).toContain(first.text);
    expect(render(state.turns)).toContain('Hindi original');
    expect(render(state.turns)).toContain('Translating…');
    state = roomReducer(
      state,
      demoEvent('translation.ready', {
        utterance_id: first.id,
        target_language: 'ta',
        text: 'நாளை காலை பத்து மணிக்கு.',
      }),
    );
    const html = render(state.turns);
    expect(html).toContain('நாளை காலை பத்து மணிக்கு.');
    expect(html).toContain(second.text);
    expect(html.indexOf(first.speaker_name)).toBeLessThan(html.indexOf(second.speaker_name));
    expect(html).not.toContain('Translating…');
  });
  it('labels the original on a failed branch without borrowing a different translation', () => {
    const turn: Turn = {
      ...makeDemoTurn(0),
      status: 'error',
      translations: { en: 'Other output' },
    };
    const html = render([turn], 'mr');
    expect(html).toContain('No Marathi translation');
    expect(html).toContain('lang="hi"');
    expect(html).toContain(turn.text);
    expect(html).not.toContain('Other output');
  });
  it.each(['hi', 'ta', 'bn', 'te', 'mr'] as const)(
    'marks readable %s captions with the listener language',
    (language) => {
      const turn = makeDemoTurn(0);
      turn.translations = { [language]: 'AM-204' };
      const html = render([turn], language);
      expect(html).toContain(`lang="${language}"`);
      expect(html).toContain(turn.source_language === language ? turn.text : 'AM-204');
    },
  );
});
