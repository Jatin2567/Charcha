import { describe, expect, it } from 'vitest';
import {
  DEFAULT_JOURNAL_FILTER,
  developerJournal,
  filterJournal,
  journalReport,
} from './developerJournal';

describe('curated developer journal', () => {
  it('combines status, area and case-insensitive root-cause search', () => {
    const matches = filterJournal(developerJournal, {
      status: 'fixed',
      area: 'measurement',
      search: '  PROCESSING EVENT  ',
    });
    expect(matches.map((entry) => entry.id)).toEqual(['honest-timing-boundaries']);
    expect(
      filterJournal(developerJournal, {
        status: 'pending',
        area: 'measurement',
        search: 'shared',
      }).map((entry) => entry.id),
    ).toEqual(['listener-latency']);
  });
  it('searches source paths without mutating or fetching source records', () => {
    const initialIds = developerJournal.map((entry) => entry.id);
    expect(
      filterJournal(developerJournal, {
        ...DEFAULT_JOURNAL_FILTER,
        search: 'verify_same_language.py',
      }).map((entry) => entry.id),
    ).toEqual(['mute-state', 'forwarding-playout']);
    expect(
      filterJournal(developerJournal, { ...DEFAULT_JOURNAL_FILTER, search: 'does-not-exist' }),
    ).toEqual([]);
    expect(developerJournal.map((entry) => entry.id)).toEqual(initialIds);
  });
  it('keeps pending acceptance visible and requires evidence and safe source references', () => {
    expect(new Set(developerJournal.map((entry) => entry.id)).size).toBe(developerJournal.length);
    expect(developerJournal.length).toBeLessThanOrEqual(25);
    for (const entry of developerJournal) {
      expect(entry.evidence.length).toBeGreaterThan(0);
      expect(entry.references.length).toBeGreaterThan(0);
      expect(entry.verification.length).toBeGreaterThan(40);
      if (entry.status === 'pending') expect(entry.outstanding).toBeTruthy();
      for (const reference of entry.references) {
        expect(reference).not.toMatch(/^(?:https?:|file:|\/|[A-Za-z]:)/);
        expect(reference.split('/')).not.toContain('..');
      }
    }
    expect(developerJournal.find((entry) => entry.id === 'real-provider-acceptance')?.status).toBe(
      'pending',
    );
    expect(developerJournal.find((entry) => entry.id === 'listener-latency')?.status).toBe(
      'pending',
    );
  });
  it('exports the visible static entries and no search query or application state', () => {
    const entries = filterJournal(developerJournal, {
      ...DEFAULT_JOURNAL_FILTER,
      area: 'security',
      search: 'URL',
    });
    const report = journalReport(entries);
    expect(Object.keys(report)).toEqual([
      'schema_version',
      'record_type',
      'last_updated',
      'scope',
      'note',
      'entry_count',
      'entries',
    ]);
    expect(report.entry_count).toBe(1);
    expect(report.entries[0].id).toBe('websocket-authentication');
    expect(report.entries[0].references).not.toBe(entries[0].references);
    expect(report.entries[0].evidence).not.toBe(entries[0].evidence);
    expect(report).not.toHaveProperty('search');
    expect(report).not.toHaveProperty('session_token');
  });
});
