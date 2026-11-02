import { describe, expect, it } from 'vitest';
import { LANGUAGES, isLanguage, SCRIPTED_LANGUAGE_CODES } from '../types/domain';
import {
  batchDelivery,
  languageRoutes,
  languageRoutingPlan,
  sourceRouting,
} from './languageCoverage';
import { shouldSubscribe } from './livekit';
import { createDemoRoom, demoLookup, joinDemo, SCRIPTED_TURNS } from './demo';

describe('expanded language routing preparation', () => {
  it('distinguishes recorded delivery from reciprocal, failed and same-language routes', () => {
    expect(batchDelivery('hi', 'ta')).toBe('Received');
    expect(batchDelivery('ta', 'hi')).toBe('—');
    expect(batchDelivery('bn', 'mr')).toBe('Failed');
    expect(batchDelivery('ta', 'ta')).toBe('Original');
  });
  it('plans unique directed pairs without same-speaker or invented provider evidence', () => {
    const routes = languageRoutes();
    expect(routes).toHaveLength(90);
    expect(
      new Set(routes.map((route) => `${route.source_language}:${route.target_language}`)).size,
    ).toBe(90);
    for (const language of LANGUAGES) {
      expect(sourceRouting(language.code)).toHaveLength(9);
      expect(
        routes.some(
          (route) =>
            route.source_language === language.code && route.target_language === language.code,
        ),
      ).toBe(false);
    }
    const report = languageRoutingPlan();
    expect(report.baseline_directed_route_count).toBe(12);
    expect(report.approval_granted).toBe(false);
    expect(report.provider_requests_made).toBe(0);
    expect(report.routes.every((route) => route.status === 'not_tested')).toBe(true);
    expect(isLanguage('or')).toBe(false);
    expect(isLanguage('hi-en')).toBe(false);
  });
  it('isolates every planned target-language subscription from direct and wrong-language audio', () => {
    for (const route of languageRoutes()) {
      const speaker = `source-${route.source_language}`;
      const name = `translated:${speaker}:${route.target_language}`;
      expect(shouldSubscribe(name, 'agent', 'self', route.target_language, 'agent')).toBe(true);
      expect(shouldSubscribe(name, 'untrusted', 'self', route.target_language, 'agent')).toBe(
        false,
      );
      expect(shouldSubscribe(name, 'agent', speaker, route.target_language, 'agent')).toBe(false);
      for (const wrong of LANGUAGES.filter((language) => language.code !== route.target_language))
        expect(shouldSubscribe(name, 'agent', 'self', wrong.code, 'agent')).toBe(false);
    }
  });
  it('keeps new language choices out of scripted output instead of inventing translations', () => {
    const added = LANGUAGES.filter((language) => !SCRIPTED_LANGUAGE_CODES.includes(language.code));
    for (const language of added) {
      expect(demoLookup(SCRIPTED_TURNS[0].text, language.code)).toBeNull();
      const room = createDemoRoom('No invented demo translation');
      expect(() => joinDemo(room.code, 'Test', language.code, 'standard')).toThrow(
        'require live setup',
      );
    }
    expect(languageRoutingPlan().languages).toHaveLength(10);
  });
});
