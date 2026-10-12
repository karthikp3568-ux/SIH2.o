/**
 * "You're closer than you think."
 *
 * The gap is framed as a short list of next skills rather than a deficit. The
 * readiness figure is the backend's weighted competency coverage for this
 * qualification — a computed number, so it is shown, and labelled for what it
 * is ("of this standard already covered"), not as a probability of success.
 */

import type { ReactNode } from 'react'

import type { SkillGapReport } from '../api/types'
import { Icon } from './Icon'
import { Chip } from './ui'

export function ReadinessRing({ value, size = 148, label }: { value: number; size?: number; label?: string }) {
  const percent = Math.max(0, Math.min(100, Math.round(value * 100)))
  const r = 52
  const circumference = 2 * Math.PI * r
  return (
    <div className="ring" style={{ width: size, height: size }} role="img" aria-label={`${percent}% ${label ?? 'covered'}`}>
      <svg viewBox="0 0 120 120" width={size} height={size}>
        <circle cx="60" cy="60" r={r} className="ring__track" />
        <circle
          cx="60"
          cy="60"
          r={r}
          className="ring__fill"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - percent / 100)}
        />
      </svg>
      <div className="ring__value">
        <strong>{percent}%</strong>
        <span>{label ?? 'covered'}</span>
      </div>
    </div>
  )
}

export function SkillGapCard({
  report,
  nextStep,
  action,
}: {
  report: SkillGapReport
  nextStep?: string | null
  action?: ReactNode
}) {
  const have = report.covered
  const partly = report.partial
  const need = report.missing
  const total = have.length + partly.length + need.length

  return (
    <div className="gap-card">
      <div className="gap-card__head">
        <ReadinessRing value={report.coverage_ratio} label="already covered" />
        <div className="grow">
          <span className="eyebrow">Towards {report.nsqf_level ? `NSQF level ${report.nsqf_level}` : 'this standard'}</span>
          <h3 className="gap-card__title">{report.qualification_title}</h3>
          <p className="small muted" style={{ margin: 0 }}>
            You already cover <strong className="ink-2">{have.length}</strong> of {total} competencies
            {partly.length > 0 ? (
              <>
                {' '}and are partly there on <strong className="ink-2">{partly.length}</strong> more
              </>
            ) : null}
            . {report.qualification_code ? `Standard ${report.qualification_code}.` : ''}
          </p>
        </div>
      </div>

      <div className="gap-card__cols">
        <section>
          <h4 className="gap-card__col-title gap-card__col-title--have">
            <Icon name="checkCircle" size={18} /> You already have
          </h4>
          <ul className="check-list">
            {have.map((c) => (
              <li key={c.code} className="enter">
                <span className="check-list__mark check-list__mark--have">
                  <Icon name="check" size={14} strokeWidth={3} />
                </span>
                <div>
                  <div className="strong">{c.name}</div>
                  <div className="check-list__detail">
                    From {c.contributing_skills.filter((s) => s.is_direct).map((s) => s.skill_name.toLowerCase()).join(', ') || 'your experience'}
                  </div>
                </div>
              </li>
            ))}
            {partly.map((c) => (
              <li key={c.code} className="enter">
                <span className="check-list__mark check-list__mark--warn">
                  <Icon name="activity" size={13} strokeWidth={2.6} />
                </span>
                <div>
                  <div className="strong">
                    {c.name} <Chip tone="warn">Partly there</Chip>
                  </div>
                  <div className="check-list__detail">{c.explanation}</div>
                </div>
              </li>
            ))}
            {have.length + partly.length === 0 ? <li className="muted small">Nothing yet — that’s fine, everyone starts somewhere.</li> : null}
          </ul>
        </section>

        <section>
          <h4 className="gap-card__col-title gap-card__col-title--need">
            <Icon name="target" size={18} /> Next skills to build
          </h4>
          {need.length === 0 ? (
            <p className="small muted">Nothing missing — you meet every competency in this standard.</p>
          ) : (
            <ul className="check-list">
              {need.map((c, index) => (
                <li key={c.code} className="enter" style={{ animationDelay: `${index * 90}ms` }}>
                  <span className="check-list__mark check-list__mark--need" aria-hidden="true" />
                  <div>
                    <div className="strong">{c.name}</div>
                    <div className="check-list__detail">
                      {c.is_core ? 'Core' : 'Elective'}
                      {c.nos_code ? ` · ${c.nos_code}` : ''}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {nextStep || action ? (
        <div className="gap-card__next">
          <span className="icon-tile icon-tile--blue icon-tile--sm">
            <Icon name="flag" size={17} />
          </span>
          <div className="grow">
            <div className="eyebrow">Recommended next step</div>
            {nextStep ? <p style={{ margin: '2px 0 0', fontWeight: 600 }}>{nextStep}</p> : null}
          </div>
          {action}
        </div>
      ) : null}
    </div>
  )
}
