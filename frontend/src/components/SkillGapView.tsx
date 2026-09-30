/** Side-by-side view: what a qualification needs vs what the person has. */

import type { CompetencyCoverage, SkillGapReport } from '../api/types'
import { Chip, Meter } from './ui'

const BAND_META: Record<string, { tone: 'good' | 'warn' | 'bad'; icon: string; label: string }> = {
  covered: { tone: 'good', icon: '✓', label: 'You can do this' },
  partial: { tone: 'warn', icon: '◐', label: 'Partly there' },
  missing: { tone: 'bad', icon: '○', label: 'To learn' },
}

function CompetencyRow({ competency }: { competency: CompetencyCoverage }) {
  const meta = BAND_META[competency.band]
  return (
    <li
      style={{
        display: 'flex',
        gap: 'var(--space-3)',
        padding: 'var(--space-3) 0',
        borderBottom: '1px dashed var(--grey-200)',
      }}
    >
      <span aria-hidden="true" style={{ fontSize: '1.1rem', lineHeight: 1.4 }}>
        {meta.icon}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="row row--between" style={{ gap: 'var(--space-2)' }}>
          <strong style={{ fontSize: '0.98rem' }}>{competency.name}</strong>
          <Chip tone={meta.tone}>{meta.label}</Chip>
        </div>
        <p className="small muted" style={{ margin: '4px 0 6px' }}>
          {competency.explanation}
        </p>
        <div className="row tiny muted" style={{ gap: 'var(--space-3)' }}>
          {competency.nos_code ? <span>Standard {competency.nos_code}</span> : null}
          {competency.is_core ? <span>Core</span> : <span>Elective</span>}
        </div>
      </div>
    </li>
  )
}

export function SkillGapView({ report }: { report: SkillGapReport }) {
  const gapLabel =
    report.gap_band === 'small'
      ? 'A little to learn'
      : report.gap_band === 'moderate'
        ? 'Some to learn'
        : 'A lot to learn'

  return (
    <div className="stack">
      <div className="card card--quiet">
        <div className="row row--between">
          <div>
            <h4 style={{ marginBottom: 2 }}>{report.qualification_title}</h4>
            <p className="tiny muted" style={{ margin: 0 }}>
              {report.qualification_code ? `${report.qualification_code} · ` : ''}
              {report.nsqf_level ? `NSQF level ${report.nsqf_level}` : 'Level not stated'}
            </p>
          </div>
          <Chip
            tone={report.gap_band === 'small' ? 'good' : report.gap_band === 'moderate' ? 'warn' : 'bad'}
            icon="◎"
          >
            {gapLabel}
          </Chip>
        </div>
        <div style={{ marginTop: 'var(--space-3)' }}>
          <Meter
            value={report.coverage_ratio}
            label="How much of this you already cover"
            tone={report.coverage_ratio >= 0.5 ? 'good' : 'warn'}
          />
        </div>
      </div>

      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {[...report.covered, ...report.partial, ...report.missing].map((competency) => (
          <CompetencyRow key={competency.code} competency={competency} />
        ))}
      </ul>

      {report.source ? (
        <p className="tiny muted">
          Standard source: {report.source}
        </p>
      ) : null}
    </div>
  )
}
