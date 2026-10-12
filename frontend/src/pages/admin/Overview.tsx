/**
 * Console overview: is the system healthy, and where do humans need to act?
 *
 * Every figure is computed live from the database by the analytics endpoint;
 * when that database holds seeded demonstration data, the page says so.
 */

import { Link } from 'react-router-dom'

import { api } from '../../api/client'
import { Icon } from '../../components/Icon'
import type { IconName } from '../../components/Icon'
import { ErrorState, Loading, opportunityState } from '../../components/ui'
import type { OpportunityState } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import type { ReviewItem } from '../../lib/adminData'

function Kpi({ icon, tone, value, label, sub }: { icon: IconName; tone: string; value: number | string; label: string; sub?: string }) {
  return (
    <div className="kpi">
      <span className={`icon-tile icon-tile--sm icon-tile--${tone}`}>
        <Icon name={icon} size={18} />
      </span>
      <div className="kpi__value">{value}</div>
      <div className="kpi__label">{label}</div>
      {sub ? <div className="kpi__sub">{sub}</div> : null}
    </div>
  )
}

const HEALTH: { state: OpportunityState; label: string; icon: IconName }[] = [
  { state: 'active', label: 'Active', icon: 'check' },
  { state: 'expiring', label: 'Expiring soon', icon: 'clock' },
  { state: 'stale', label: 'Stale (90+ days)', icon: 'alert' },
  { state: 'unverified', label: 'Unverified', icon: 'circle' },
  { state: 'inactive', label: 'Inactive / expired', icon: 'x' },
]

export function Overview({ queue }: { queue: { items: ReviewItem[]; pendingCount: number } | null }) {
  const data = useAsync(async () => {
    const [analytics, opps] = await Promise.all([api.analytics(), api.adminOpportunities({ limit: '200' })])
    return { analytics, opps }
  }, [])

  if (data.loading) return <Loading label="Loading the overview…" />
  if (data.error || !data.data) return <ErrorState message="We couldn’t load the overview." onRetry={data.reload} />

  const { analytics: a, opps } = data.data
  const o = a.outcomes as Record<string, number>
  const livelihood = (o.employed ?? 0) + (o.self_employed ?? 0)

  const health = new Map<OpportunityState, number>()
  for (const item of opps.items) {
    const state = opportunityState(item)
    health.set(state, (health.get(state) ?? 0) + 1)
  }
  const healthTotal = opps.items.length || 1

  const gaps = a.top_skill_gaps.slice(0, 6)
  const gapMax = Math.max(1, ...gaps.map((g) => g.count))

  const pipeline: { label: string; value: number; icon: IconName }[] = [
    { label: 'Chosen', value: a.recommendations.selected, icon: 'route' },
    { label: 'Enrolled', value: o.enrolled ?? 0, icon: 'edit' },
    { label: 'Training', value: o.attending ?? 0, icon: 'book' },
    { label: 'Completed', value: o.completed ?? 0, icon: 'cap' },
    { label: 'Livelihood', value: livelihood, icon: 'sprout' },
  ]

  return (
    <div className="admin-stack">
      {a.is_demo_data ? (
        <div className="demo-banner">
          <Icon name="info" size={16} />
          {a.disclaimer ?? 'Figures are computed live from the seeded demonstration data in this database.'}
        </div>
      ) : null}

      <div className="kpi-row">
        <Kpi icon="users" tone="blue" value={a.beneficiaries.total} label="Beneficiaries" sub={`${a.beneficiaries.profile_confirmed} confirmed profiles`} />
        <Kpi icon="briefcase" tone="teal" value={a.opportunities.active} label="Active opportunities" sub={`${a.opportunities.verified} staff-verified`} />
        <Kpi icon="sparkle" tone="blue" value={a.recommendations.generated} label="Recommendations" sub={`${a.recommendations.runs} ranking runs`} />
        <Kpi icon="edit" tone="amber" value={o.enrolled ?? 0} label="Training enrolments" sub={`${a.recommendations.selected} pathways chosen`} />
        <Kpi icon="cap" tone="teal" value={o.completed ?? 0} label="Completions" />
        <Kpi icon="sprout" tone="teal" value={livelihood} label="Livelihood outcomes" sub="Working or self-employed" />
      </div>

      <div className="admin-grid">
        <section className="panel">
          <header className="panel__head">
            <h2>Recommendation health</h2>
            <Link to="/admin/recommendations" className="panel__link">
              Review <Icon name="arrowRight" size={14} />
            </Link>
          </header>
          <dl className="mini-stats">
            <div>
              <dt>Acceptance</dt>
              <dd>{a.recommendations.acceptance_rate !== null ? `${Math.round(a.recommendations.acceptance_rate * 100)}%` : '—'}</dd>
            </div>
            <div>
              <dt>No-match runs</dt>
              <dd>{a.recommendations.no_match_runs}</dd>
            </div>
            <div>
              <dt>Avg. distance</dt>
              <dd>{a.recommendations.average_distance_km !== null ? `${a.recommendations.average_distance_km} km` : '—'}</dd>
            </div>
            <div>
              <dt>Overridden</dt>
              <dd>{a.recommendations.overridden}</dd>
            </div>
          </dl>
          <h3 className="panel__sub">Top skill gaps</h3>
          {gaps.length === 0 ? (
            <p className="small muted">No recommendations generated yet.</p>
          ) : (
            <ul className="hbars">
              {gaps.map((g) => (
                <li key={g.code} title={`${g.name}: missing in ${g.count} recommendations`}>
                  <span className="hbars__label">{g.name}</span>
                  <span className="hbars__track">
                    <span className="hbars__fill" style={{ width: `${(g.count / gapMax) * 100}%` }} />
                  </span>
                  <span className="hbars__value">{g.count}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="tiny muted" style={{ margin: 'var(--space-3) 0 0' }}>
            Count of recommendations in which each competency is missing — where new training would help most.
          </p>
        </section>

        <section className="panel">
          <header className="panel__head">
            <h2>Opportunity health</h2>
            <Link to="/admin/verification" className="panel__link">
              Verify <Icon name="arrowRight" size={14} />
            </Link>
          </header>
          <div className="health-bar" role="img" aria-label={HEALTH.map((h) => `${h.label} ${health.get(h.state) ?? 0}`).join(', ')}>
            {HEALTH.filter((h) => health.get(h.state)).map((h) => (
              <span
                key={h.state}
                className={`health-bar__seg health-bar__seg--${h.state}`}
                style={{ width: `${((health.get(h.state) ?? 0) / healthTotal) * 100}%` }}
                title={`${h.label}: ${health.get(h.state)}`}
              />
            ))}
          </div>
          <ul className="health-list">
            {HEALTH.map((h) => (
              <li key={h.state}>
                <span className={`status-chip status-chip--${h.state}`}>
                  <Icon name={h.icon} size={12} strokeWidth={3} />
                  {h.label}
                </span>
                <span className="health-list__value">{health.get(h.state) ?? 0}</span>
              </li>
            ))}
          </ul>
          <p className="tiny muted" style={{ margin: 'var(--space-3) 0 0' }}>
            Listings unverified for over a year are excluded from matching automatically ({a.opportunities.excluded_as_hard_stale} now).
          </p>
        </section>

        <section className="panel panel--queue">
          <header className="panel__head">
            <h2>AI review queue</h2>
          </header>
          <div className="queue-hero">
            <span className="queue-hero__value">{queue?.pendingCount ?? '—'}</span>
            <span>recommendations awaiting human review</span>
          </div>
          <ul className="queue-list">
            {(queue?.items ?? [])
              .filter((i) => i.pending.length > 0)
              .slice(0, 4)
              .map((item) => (
                <li key={item.beneficiary.id}>
                  <span className="queue-list__avatar">{item.beneficiary.display_name.charAt(0)}</span>
                  <span className="grow">
                    <strong>{item.beneficiary.display_name}</strong>
                    <span className="tiny muted">{item.beneficiary.district ?? 'District not set'}</span>
                  </span>
                  <span className="queue-list__count">{item.pending.length}</span>
                </li>
              ))}
          </ul>
          <Link to="/admin/recommendations" className="btn btn--dark btn--block">
            Open review queue <Icon name="arrowRight" size={16} />
          </Link>
        </section>
      </div>

      <section className="panel">
        <header className="panel__head">
          <h2>Outcome pipeline</h2>
          <Link to="/admin/outcomes" className="panel__link">
            Outcomes <Icon name="arrowRight" size={14} />
          </Link>
        </header>
        <ol className="pipeline">
          {pipeline.map((step, i) => (
            <li key={step.label} className={i === pipeline.length - 1 ? 'is-last' : ''}>
              <span className="pipeline__icon">
                <Icon name={step.icon} size={18} />
              </span>
              <span className="pipeline__value">{step.value}</span>
              <span className="pipeline__label">{step.label}</span>
            </li>
          ))}
        </ol>
        <p className="tiny muted" style={{ margin: 'var(--space-3) 0 0' }}>
          Recorded by beneficiaries and staff as each milestone happens. {o.dropped_out ? `${o.dropped_out} stopped along the way.` : ''}
        </p>
      </section>
    </div>
  )
}
