/**
 * Outcomes — whether recommendations turned into livelihoods.
 *
 * This is the learning signal: milestone counts show where people drop off,
 * and structured feedback reasons show why.
 */

import { api } from '../../api/client'
import type { Outcome } from '../../api/types'
import { Icon } from '../../components/Icon'
import type { IconName } from '../../components/Icon'
import { Chip, EmptyState, ErrorState, Loading, formatDate, formatInr } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import type { BeneficiaryRow } from '../../lib/adminData'
import { OUTCOME_WORD } from '../../lib/labels'

export function Outcomes() {
  const data = useAsync(async () => {
    const [analytics, beneficiaries] = await Promise.all([api.analytics(), api.adminBeneficiaries() as Promise<BeneficiaryRow[]>])
    const lists = await Promise.all(
      beneficiaries.map((b) => api.outcomesFor(b.id).then((rows) => rows.map((o) => ({ o, b }))).catch(() => [])),
    )
    return { analytics, rows: lists.flat() as { o: Outcome; b: BeneficiaryRow }[] }
  }, [])

  if (data.loading) return <Loading label="Loading outcomes…" />
  if (data.error || !data.data) return <ErrorState message="We couldn’t load outcomes." onRetry={data.reload} />

  const { analytics: a, rows } = data.data
  const o = a.outcomes as Record<string, number>
  const funnel: { label: string; value: number; icon: IconName }[] = [
    { label: 'Recommended', value: a.recommendations.generated, icon: 'sparkle' },
    { label: 'Chosen', value: a.recommendations.selected, icon: 'route' },
    { label: 'Enrolled', value: o.enrolled ?? 0, icon: 'edit' },
    { label: 'Training', value: o.attending ?? 0, icon: 'book' },
    { label: 'Completed', value: o.completed ?? 0, icon: 'cap' },
    { label: 'Livelihood', value: (o.employed ?? 0) + (o.self_employed ?? 0), icon: 'sprout' },
  ]
  const top = Math.max(1, funnel[0].value)
  const reasons = a.feedback.rejection_reasons
  const reasonMax = Math.max(1, ...reasons.map((r) => r.count))

  return (
    <div className="admin-stack">
      <section className="panel">
        <header className="panel__head">
          <h2>From recommendation to livelihood</h2>
        </header>
        <ol className="funnel">
          {funnel.map((step) => (
            <li key={step.label} title={`${step.label}: ${step.value}`}>
              <span className="funnel__label">
                <Icon name={step.icon} size={16} /> {step.label}
              </span>
              <span className="funnel__track">
                <span className="funnel__fill" style={{ width: `${Math.max(step.value ? 2 : 0, (step.value / top) * 100)}%` }} />
              </span>
              <span className="funnel__value">{step.value}</span>
            </li>
          ))}
        </ol>
        {o.dropped_out ? (
          <p className="small muted" style={{ margin: 'var(--space-3) 0 0' }}>
            {o.dropped_out} stopped part-way. Their reasons are below.
          </p>
        ) : null}
      </section>

      <div className="admin-grid admin-grid--2">
        <section className="panel">
          <header className="panel__head">
            <h2>Beneficiary feedback</h2>
          </header>
          <dl className="mini-stats">
            <div>
              <dt>Responses</dt>
              <dd>{a.feedback.total}</dd>
            </div>
            <div>
              <dt>Found it useful</dt>
              <dd>{a.feedback.total ? `${Math.round((a.feedback.found_useful / a.feedback.total) * 100)}%` : '—'}</dd>
            </div>
            <div>
              <dt>Average rating</dt>
              <dd>{a.feedback.average_rating !== null ? `${a.feedback.average_rating.toFixed(1)} / 5` : '—'}</dd>
            </div>
          </dl>
        </section>
        <section className="panel">
          <header className="panel__head">
            <h2>Why pathways didn’t work</h2>
          </header>
          {reasons.length === 0 ? (
            <p className="small muted">No problems reported yet.</p>
          ) : (
            <ul className="hbars hbars--amber">
              {reasons.map((r) => (
                <li key={r.code} title={`${r.label}: ${r.count}`}>
                  <span className="hbars__label">{r.label}</span>
                  <span className="hbars__track">
                    <span className="hbars__fill" style={{ width: `${(r.count / reasonMax) * 100}%` }} />
                  </span>
                  <span className="hbars__value">{r.count}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="panel panel--flush">
        <header className="panel__head" style={{ padding: 'var(--space-4) var(--space-5) 0' }}>
          <h2>Outcome records</h2>
        </header>
        {rows.length === 0 ? (
          <EmptyState icon="flag" title="No pathways chosen yet" description="Outcomes appear once a beneficiary chooses a pathway." />
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Beneficiary</th>
                  <th>Pathway</th>
                  <th>Status</th>
                  <th>Chosen</th>
                  <th>Income</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ o: outcome, b }) => (
                  <tr key={outcome.id}>
                    <td>
                      <strong>{b.display_name}</strong>
                    </td>
                    <td className="small">
                      {outcome.opportunity?.title ?? '—'}
                      <div className="tiny muted">{outcome.opportunity?.provider}</div>
                    </td>
                    <td>
                      <Chip tone={['employed', 'self_employed', 'completed'].includes(outcome.status) ? 'good' : ['dropped_out', 'rejected'].includes(outcome.status) ? 'bad' : 'info'}>
                        {OUTCOME_WORD[outcome.status] ?? outcome.status}
                      </Chip>
                    </td>
                    <td className="small nowrap">{formatDate(outcome.selected_at)}</td>
                    <td className="small">{formatInr(outcome.monthly_income_inr) ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
