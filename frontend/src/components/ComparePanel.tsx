/**
 * Pathways side by side, on the factors that decided their order.
 *
 * Bars are the engine's own factor scores; the words next to them carry the
 * meaning so nobody has to read the bar length precisely.
 */

import { api } from '../api/client'
import type { Explanation, Recommendation } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { matchLabel } from '../lib/labels'
import { availabilityWord, eligibilityWord, factor, gapWord, strengthWord } from '../lib/pathway'
import { Icon } from './Icon'
import { Loading } from './ui'

function Bar({ value }: { value: number | undefined }) {
  if (value === undefined) return <span className="muted">—</span>
  const filled = Math.round(value * 10)
  return (
    <span className="seg-bar" aria-label={`${strengthWord(value)}`}>
      <span className="seg-bar__cells" aria-hidden="true">
        {Array.from({ length: 10 }, (_, i) => (
          <span key={i} className={i < filled ? (value >= 0.6 ? 'is-good' : value < 0.4 ? 'is-weak' : 'is-mid') : ''} />
        ))}
      </span>
      <span className="seg-bar__word">{strengthWord(value)}</span>
    </span>
  )
}

function Yes({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`yes ${ok ? 'is-ok' : 'is-no'}`}>
      <Icon name={ok ? 'check' : 'x'} size={14} strokeWidth={3} /> {label}
    </span>
  )
}

export function ComparePanel({ recs, onOpen }: { recs: Recommendation[]; onOpen: (rec: Recommendation) => void }) {
  const explanations = useAsync(
    () => Promise.all(recs.map((r) => api.explanation(r.id).catch(() => null))),
    [recs.map((r) => r.id).join(',')],
  )

  if (explanations.loading) return <Loading label="Lining up your pathways…" />
  const byId = new Map<string, Explanation | null>(recs.map((r, i) => [r.id, explanations.data?.[i] ?? null]))

  const rows: { label: string; render: (r: Recommendation, e: Explanation | null) => React.ReactNode }[] = [
    { label: 'Overall', render: (r) => <span className={`match-pill match-pill--${matchLabel(r.match_score).tone}`}>{matchLabel(r.match_score).label}</span> },
    { label: 'Skill fit', render: (_, e) => <Bar value={factor(e?.factors, 'skill_fit')?.score} /> },
    {
      label: 'Location',
      render: (r, e) => (
        <div>
          <Bar value={factor(e?.factors, 'location_fit')?.score} />
          <div className="tiny muted">{r.distance_km !== null ? `${Math.round(r.distance_km)} km away` : 'Distance unknown'}</div>
        </div>
      ),
    },
    { label: 'Travel needed', render: (_, e) => <Bar value={factor(e?.factors, 'mobility_fit')?.score} /> },
    { label: 'Eligibility', render: (r) => <Yes ok={eligibilityWord(r).ok} label={eligibilityWord(r).label} /> },
    { label: 'Availability', render: (r) => <Yes ok={availabilityWord(r).ok} label={availabilityWord(r).label} /> },
    {
      label: 'Skill gap',
      render: (r) => (
        <div>
          <span className={`gap-word gap-word--${r.skill_gap}`}>{gapWord(r)}</span>
          {r.missing_competencies.length ? (
            <div className="tiny muted">
              {r.missing_competencies.length} not covered at all
            </div>
          ) : null}
        </div>
      ),
    },
  ]

  return (
    <div className="compare enter">
      <div className="compare__scroll">
        <table className="compare__table">
          <thead>
            <tr>
              <th scope="col">
                <span className="visually-hidden">Factor</span>
              </th>
              {recs.map((r) => (
                <th key={r.id} scope="col">
                  <span className="compare__rank">{r.rank}</span>
                  <button type="button" className="compare__title" onClick={() => onOpen(r)}>
                    {r.qualification?.title ?? r.title}
                  </button>
                  <div className="tiny muted">{r.provider}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <th scope="row">{row.label}</th>
                {recs.map((r) => (
                  <td key={r.id}>{row.render(r, byId.get(r.id) ?? null)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
