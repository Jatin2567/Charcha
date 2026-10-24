import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronDown,
  CircleDashed,
  Download,
  FileCode2,
  Filter,
  GitBranch,
  Search,
  Sparkles,
} from 'lucide-react';
import { Badge, PageHeading, downloadJson } from '../components/ui';
import {
  DEFAULT_JOURNAL_FILTER,
  JOURNAL_AREA_LABELS,
  JOURNAL_EVIDENCE_LABELS,
  JOURNAL_STATUS_LABELS,
  developerJournal,
  filterJournal,
  journalReport,
} from '../data/developerJournal';
import type { DeveloperJournalEntry, JournalFilter } from '../data/developerJournal';
import './DeveloperJournal.css';

function JournalCard({ entry }: { entry: DeveloperJournalEntry }) {
  return (
    <details className={`journal-entry journal-entry-${entry.status}`}>
      <summary>
        <span className={`journal-entry-marker journal-marker-${entry.status}`} aria-hidden="true">
          {entry.status === 'fixed' ? (
            <Check size={17} />
          ) : entry.status === 'improved' ? (
            <Sparkles size={16} />
          ) : (
            <CircleDashed size={17} />
          )}
        </span>
        <span className="journal-entry-copy">
          <span className="journal-entry-meta">
            <span>{JOURNAL_AREA_LABELS[entry.area]}</span>
            <span aria-hidden="true">·</span>
            <time dateTime={entry.date}>24 Oct 2026</time>
          </span>
          <strong>{entry.title}</strong>
          <span className="journal-entry-summary">{entry.summary}</span>
        </span>
        <Badge
          tone={
            entry.status === 'fixed' ? 'green' : entry.status === 'pending' ? 'orange' : 'neutral'
          }
        >
          {JOURNAL_STATUS_LABELS[entry.status]}
        </Badge>
        <ChevronDown className="journal-entry-chevron" size={18} aria-hidden="true" />
      </summary>
      <div className="journal-entry-body">
        <div className="journal-detail-grid">
          <section>
            <h3>What caused it</h3>
            <p>{entry.cause}</p>
          </section>
          <section>
            <h3>What changed</h3>
            <p>{entry.change}</p>
          </section>
        </div>
        <section className="journal-verification">
          <h3>Evidence & verification</h3>
          <p>{entry.verification}</p>
          <div className="journal-evidence-tags">
            {entry.evidence.map((evidence) => (
              <span key={evidence}>{JOURNAL_EVIDENCE_LABELS[evidence]}</span>
            ))}
          </div>
        </section>
        {entry.outstanding && (
          <section className="journal-outstanding">
            <h3>Still to check</h3>
            <p>{entry.outstanding}</p>
          </section>
        )}
        <div className="journal-references">
          <span>
            <FileCode2 size={13} /> Source reference
          </span>
          <div>
            {entry.references.map((reference) => (
              <code key={reference}>{reference}</code>
            ))}
          </div>
          <small>Paths refer to the downloadable project source.</small>
        </div>
      </div>
    </details>
  );
}

export function DeveloperJournal() {
  const [filter, setFilter] = useState<JournalFilter>(DEFAULT_JOURNAL_FILTER);
  const entries = useMemo(() => filterJournal(developerJournal, filter), [filter]);
  const update = <K extends keyof JournalFilter>(key: K, value: JournalFilter[K]) =>
    setFilter((current) => ({ ...current, [key]: value }));
  const filtered =
    filter.status !== 'all' || filter.area !== 'all' || Boolean(filter.search.trim());
  return (
    <div className="development-page">
      <PageHeading
        eyebrow="BUILDING IN THE OPEN"
        title="Developer journal"
        description="The decisions, fixes and remaining checks behind a conversation that works."
        action={
          <button
            className="button secondary"
            onClick={() => downloadJson('artha-mesh-development.json', journalReport(entries))}
          >
            <Download size={16} />
            Export notes
          </button>
        }
      />
      <section className="journal-intro" aria-labelledby="journal-intro-title">
        <span className="journal-intro-icon">
          <GitBranch size={25} />
        </span>
        <div>
          <div className="journal-intro-heading">
            <h2 id="journal-intro-title">A record of the work, with its limits</h2>
            <Badge tone="green">Track B</Badge>
          </div>
          <p>
            Manually maintained engineering notes, last reviewed 24 October 2026. Each entry
            explains the cause, change and evidence. This is not a live issue tracker or a log of
            your conversations.
          </p>
        </div>
      </section>
      <div className="journal-summary-grid" aria-label="Journal overview">
        {[
          {
            status: 'fixed' as const,
            title: 'Bugs resolved',
            description: 'Recorded fixes with local evidence',
            icon: Check,
          },
          {
            status: 'improved' as const,
            title: 'Improvements',
            description: 'Stronger routing, access and reporting',
            icon: Sparkles,
          },
          {
            status: 'pending' as const,
            title: 'Open checks',
            description: 'Work or external evidence still needed',
            icon: CircleDashed,
          },
        ].map(({ status, title, description, icon: Icon }) => (
          <button
            key={status}
            className={`journal-summary-card ${filter.status === status ? 'is-selected' : ''}`}
            onClick={() => update('status', filter.status === status ? 'all' : status)}
            aria-pressed={filter.status === status}
          >
            <span className={`journal-stat-icon journal-marker-${status}`}>
              <Icon size={18} />
            </span>
            <div>
              <span>{title}</span>
              <strong>{developerJournal.filter((entry) => entry.status === status).length}</strong>
              <small>{description}</small>
            </div>
          </button>
        ))}
      </div>
      <section className="journal-evidence-guide" aria-labelledby="journal-evidence-title">
        <BookOpen size={19} />
        <div>
          <h2 id="journal-evidence-title">Read the evidence at the right level</h2>
          <p>
            Automated checks validate specific behavior. Synthetic WebRTC uses generated audio and
            provider doubles. Browser checks cover interaction. Approved API checks record bounded
            calls to the real service. Real translation quality, cloned
            voice similarity and audible listener delay still require live accounts and consenting
            speakers.
          </p>
        </div>
        <Link className="text-link" to="/performance">
          Measurement reference
          <ArrowUpRight size={15} />
        </Link>
      </section>
      <section className="journal-records" aria-labelledby="journal-records-title">
        <div className="journal-records-heading">
          <div>
            <span className="eyebrow">ENGINEERING RECORD</span>
            <h2 id="journal-records-title">What we learned & changed</h2>
          </div>
          <span>
            {entries.length} of {developerJournal.length} notes
          </span>
        </div>
        <div className="journal-filter-bar">
          <label className="journal-search">
            <Search size={17} aria-hidden="true" />
            <span className="journal-visually-hidden">Search developer notes</span>
            <input
              type="search"
              value={filter.search}
              placeholder="Search bugs, fixes or source paths…"
              onChange={(event) => update('search', event.target.value)}
            />
          </label>
          <label className="journal-select">
            <span>Status</span>
            <select
              value={filter.status}
              onChange={(event) => update('status', event.target.value as JournalFilter['status'])}
            >
              <option value="all">All statuses</option>
              {Object.entries(JOURNAL_STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="journal-select">
            <span>Area</span>
            <select
              value={filter.area}
              onChange={(event) => update('area', event.target.value as JournalFilter['area'])}
            >
              <option value="all">All areas</option>
              {Object.entries(JOURNAL_AREA_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {filtered && (
            <button className="journal-clear" onClick={() => setFilter(DEFAULT_JOURNAL_FILTER)}>
              Clear filters
            </button>
          )}
        </div>
        <p className="journal-filter-note">
          Open a note for its root cause, verification and source references. Searching and
          exporting this page make no provider API calls.
        </p>
        <div className="journal-timeline" aria-live="polite">
          {entries.length ? (
            entries.map((entry) => <JournalCard key={entry.id} entry={entry} />)
          ) : (
            <div className="journal-empty">
              <Filter size={25} />
              <h3>No notes match these filters</h3>
              <p>Try another area or a shorter search.</p>
              <button
                className="button secondary"
                onClick={() => setFilter(DEFAULT_JOURNAL_FILTER)}
              >
                Show all notes
              </button>
            </div>
          )}
        </div>
      </section>
      <footer className="journal-footer">
        <GitBranch size={16} />
        <p>
          Maintained in <code>web/src/data/developerJournal.ts</code>. Future entries should include
          an observed problem, the actual change and its verification. Pending checks stay pending
          until evidence exists.
        </p>
      </footer>
    </div>
  );
}
