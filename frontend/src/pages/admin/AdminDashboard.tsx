/**
 * Administrator and counsellor console.
 *
 * The governing idea: an AI recommendation is a proposal. Staff can verify the
 * data behind it, correct the profile that produced it, and accept, edit or
 * reject the recommendation itself — and every one of those actions lands in
 * the audit trail.
 */

import { useState } from 'react'

import { api } from '../../api/client'
import { Layout } from '../../components/Layout'
import {
  Button,
  Card,
  Chip,
  EmptyState,
  ErrorState,
  Loading,
  Notice,
  VerificationChip,
  daysAgo,
  formatDate,
} from '../../components/ui'
import { useAction, useAsync } from '../../hooks/useAsync'
import { useApp } from '../../state/AppContext'
import type { Opportunity } from '../../api/types'
import { OpportunityEditor } from './OpportunityEditor'

type Tab = 'overview' | 'opportunities' | 'beneficiaries' | 'audit'

function Overview() {
  const analytics = useAsync(() => api.analytics(), [])

  if (analytics.loading) return <Loading />
  if (analytics.error || !analytics.data)
    return <ErrorState message={analytics.error ?? 'Could not load analytics.'} onRetry={analytics.reload} />

  const data = analytics.data

  return (
    <div className="stack">
      {data.is_demo_data ? (
        <Notice tone="warn" title="These are demonstration figures">
          <p className="small" style={{ margin: 0 }}>
            {data.disclaimer ??
              'All figures are computed from the seeded demonstration data in this database.'}
          </p>
        </Notice>
      ) : null}

      <div className="grid grid--4">
        <div className="stat">
          <div className="stat__value">{data.beneficiaries.total}</div>
          <div className="stat__label">Beneficiaries</div>
        </div>
        <div className="stat">
          <div className="stat__value">{data.opportunities.active}</div>
          <div className="stat__label">Active opportunities</div>
        </div>
        <div className="stat">
          <div className="stat__value">{data.recommendations.generated}</div>
          <div className="stat__label">Recommendations made</div>
        </div>
        <div className="stat">
          <div className="stat__value">{data.recommendations.selected}</div>
          <div className="stat__label">Pathways chosen</div>
        </div>
      </div>

      <div className="grid grid--2">
        <Card>
          <h3>Opportunity data quality</h3>
          <ul className="reason-list">
            <li>
              <span className="reason-list__icon">●</span>
              <span className="small" style={{ flex: 1 }}>Verified by staff</span>
              <span className="small strong">{data.opportunities.verified}</span>
            </li>
            <li>
              <span className="reason-list__icon">⏳</span>
              <span className="small" style={{ flex: 1 }}>Need re-verification (90+ days)</span>
              <span className="small strong">{data.opportunities.stale_needs_reverification}</span>
            </li>
            <li>
              <span className="reason-list__icon">✕</span>
              <span className="small" style={{ flex: 1 }}>Expired</span>
              <span className="small strong">{data.opportunities.expired}</span>
            </li>
            <li>
              <span className="reason-list__icon">🚫</span>
              <span className="small" style={{ flex: 1 }}>Excluded as unverified over a year</span>
              <span className="small strong">{data.opportunities.excluded_as_hard_stale}</span>
            </li>
          </ul>
        </Card>

        <Card>
          <h3>Matching</h3>
          <ul className="reason-list">
            <li>
              <span className="reason-list__icon">▦</span>
              <span className="small" style={{ flex: 1 }}>Runs</span>
              <span className="small strong">{data.recommendations.runs}</span>
            </li>
            <li>
              <span className="reason-list__icon">∅</span>
              <span className="small" style={{ flex: 1 }}>Runs with no match</span>
              <span className="small strong">{data.recommendations.no_match_runs}</span>
            </li>
            <li>
              <span className="reason-list__icon">✓</span>
              <span className="small" style={{ flex: 1 }}>Acceptance rate</span>
              <span className="small strong">
                {data.recommendations.acceptance_rate !== null
                  ? `${Math.round(data.recommendations.acceptance_rate * 100)}%`
                  : '—'}
              </span>
            </li>
            <li>
              <span className="reason-list__icon">📍</span>
              <span className="small" style={{ flex: 1 }}>Average distance recommended</span>
              <span className="small strong">
                {data.recommendations.average_distance_km !== null
                  ? `${data.recommendations.average_distance_km} km`
                  : '—'}
              </span>
            </li>
            <li>
              <span className="reason-list__icon">✎</span>
              <span className="small" style={{ flex: 1 }}>Overridden by staff</span>
              <span className="small strong">{data.recommendations.overridden}</span>
            </li>
          </ul>
        </Card>
      </div>

      <div className="grid grid--2">
        <Card>
          <h3>Outcomes</h3>
          {Object.keys(data.outcomes.by_status ?? {}).length === 0 ? (
            <p className="small muted">No outcomes recorded yet.</p>
          ) : (
            <ul className="reason-list">
              {Object.entries(data.outcomes.by_status as Record<string, number>).map(([status, count]) => (
                <li key={status}>
                  <span className="reason-list__icon">•</span>
                  <span className="small" style={{ flex: 1 }}>{status.replace(/_/g, ' ')}</span>
                  <span className="small strong">{count}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <h3>Most common skill gaps</h3>
          {data.top_skill_gaps.length === 0 ? (
            <p className="small muted">No recommendations generated yet.</p>
          ) : (
            <ul className="reason-list">
              {data.top_skill_gaps.slice(0, 8).map((gap) => (
                <li key={gap.code}>
                  <span className="reason-list__icon">○</span>
                  <span className="small" style={{ flex: 1 }}>{gap.name}</span>
                  <span className="small strong">{gap.count}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card>
        <h3>Listings most in need of re-verification</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Listing</th>
                <th>Provider</th>
                <th>Status</th>
                <th>Verification</th>
                <th>Last checked</th>
              </tr>
            </thead>
            <tbody>
              {data.opportunity_freshness.slice(0, 10).map((row) => (
                <tr key={row.id}>
                  <td>{row.title}</td>
                  <td className="muted">{row.provider}</td>
                  <td>
                    <Chip tone={row.status === 'active' ? 'good' : 'warn'}>{row.status}</Chip>
                  </td>
                  <td>
                    <VerificationChip status={row.verification_status} />
                  </td>
                  <td className="nowrap">{daysAgo(row.last_verified_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

function Opportunities() {
  const [needsReview, setNeedsReview] = useState(false)
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<Opportunity | 'new' | null>(null)
  const [importReport, setImportReport] = useState<Record<string, any> | null>(null)

  const list = useAsync(
    () => api.adminOpportunities({ ...(query ? { q: query } : {}), ...(needsReview ? { needs_review: 'true' } : {}) }),
    [query, needsReview],
  )

  const verify = useAction(async (id: string) => {
    await api.verifyOpportunity(id, {
      verification_status: 'admin_verified',
      note: 'Checked against the source',
      extend_valid_days: 90,
    })
    list.reload()
    return true
  })

  const deactivate = useAction(async (id: string) => {
    await api.deleteOpportunity(id)
    list.reload()
    return true
  })

  const doImport = useAction(async (file: File, dryRun: boolean) => {
    const report = await api.importOpportunities(file, dryRun)
    setImportReport(report)
    if (!dryRun) list.reload()
    return report
  })

  if (editing) {
    return (
      <OpportunityEditor
        opportunity={editing === 'new' ? null : editing}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null)
          list.reload()
        }}
      />
    )
  }

  return (
    <div className="stack">
      <div className="row row--between">
        <h2 style={{ margin: 0 }}>Opportunities</h2>
        <Button icon="+" onClick={() => setEditing('new')}>
          Add opportunity
        </Button>
      </div>

      <Card>
        <div className="row">
          <div style={{ flex: 1, minWidth: 220 }}>
            <label htmlFor="search" className="visually-hidden">
              Search
            </label>
            <input
              id="search"
              type="text"
              placeholder="Search by title or provider"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <label className="checkbox" style={{ minWidth: 200 }}>
            <input
              type="checkbox"
              checked={needsReview}
              onChange={(event) => setNeedsReview(event.target.checked)}
            />
            <span>Only those needing review</span>
          </label>
        </div>

        <hr className="divider" />

        <div className="row">
          <label htmlFor="csv" className="btn btn--secondary" style={{ margin: 0 }}>
            📄 Choose CSV
            <input
              id="csv"
              type="file"
              accept=".csv,text/csv"
              className="visually-hidden"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) void doImport.run(file, true)
              }}
            />
          </label>
          <span className="small muted">
            Import runs as a dry run first and reports every row it would reject.
          </span>
        </div>

        {importReport ? (
          <Notice
            tone={importReport.errors?.length ? 'warn' : 'success'}
            title={importReport.dry_run ? 'Dry run result' : 'Import complete'}
          >
            <p className="small" style={{ marginBottom: 'var(--space-2)' }}>
              {importReport.rows_read} row(s) read · {importReport.created} to create ·{' '}
              {importReport.updated} to update · {importReport.skipped} skipped
            </p>
            {(importReport.errors ?? []).length > 0 ? (
              <ul className="small" style={{ margin: 0, paddingLeft: '1.2rem' }}>
                {(importReport.errors as { row: number; errors: string[] }[]).slice(0, 8).map((error) => (
                  <li key={error.row}>
                    Row {error.row}: {error.errors.join('; ')}
                  </li>
                ))}
              </ul>
            ) : null}
            <p className="tiny muted" style={{ marginTop: 'var(--space-2)', marginBottom: 0 }}>
              Imported records are created as drafts and marked unverified — importing is not
              verifying.
            </p>
          </Notice>
        ) : null}
      </Card>

      {list.loading ? <Loading /> : null}
      {list.error ? <ErrorState message={list.error} onRetry={list.reload} /> : null}

      {list.data ? (
        <Card className="card--flush">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Listing</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Verification</th>
                  <th>Valid until</th>
                  <th>Seats</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((opportunity) => (
                  <tr key={opportunity.id}>
                    <td>
                      <strong>{opportunity.title}</strong>
                      <div className="tiny muted">{opportunity.provider}</div>
                      <div className="tiny muted">Source: {opportunity.source}</div>
                    </td>
                    <td className="nowrap">{opportunity.opportunity_type.replace('_', ' ')}</td>
                    <td>
                      <Chip tone={opportunity.status === 'active' ? 'good' : 'warn'}>
                        {opportunity.status}
                      </Chip>
                    </td>
                    <td>
                      <VerificationChip status={opportunity.verification_status} />
                      <div className="tiny muted">checked {daysAgo(opportunity.last_verified_at)}</div>
                    </td>
                    <td className="nowrap">{formatDate(opportunity.valid_until)}</td>
                    <td className="nowrap">
                      {opportunity.seats_available ?? '—'}
                      {opportunity.seats_total ? ` / ${opportunity.seats_total}` : ''}
                    </td>
                    <td>
                      <div className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
                        <Button variant="secondary" onClick={() => setEditing(opportunity)}>
                          Edit
                        </Button>
                        <Button
                          variant="secondary"
                          onClick={() => verify.run(opportunity.id)}
                          loading={verify.pending}
                        >
                          Verify
                        </Button>
                        {opportunity.status === 'active' ? (
                          <Button
                            variant="danger"
                            onClick={() => deactivate.run(opportunity.id)}
                            loading={deactivate.pending}
                          >
                            Deactivate
                          </Button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}
    </div>
  )
}

function Beneficiaries() {
  const [selected, setSelected] = useState<string | null>(null)
  const [overrideFor, setOverrideFor] = useState<string | null>(null)
  const [note, setNote] = useState('')

  const list = useAsync(() => api.adminBeneficiaries(), [])
  const detail = useAsync(
    () => (selected ? api.adminExtraction(selected) : Promise.resolve(null)),
    [selected],
  )
  const recommendations = useAsync(
    () => (selected ? api.adminRecommendations(selected).catch(() => null) : Promise.resolve(null)),
    [selected],
  )

  const override = useAction(async (recommendationId: string, action: string) => {
    await api.overrideRecommendation(recommendationId, { action, note })
    setNote('')
    setOverrideFor(null)
    recommendations.reload()
    return true
  })

  if (list.loading) return <Loading />
  if (list.error) return <ErrorState message={list.error} onRetry={list.reload} />

  return (
    <div className="stack">
      <h2>Beneficiaries</h2>

      <Card className="card--flush">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Language</th>
                <th>District</th>
                <th>Travel</th>
                <th>Skills</th>
                <th>Profile</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(list.data ?? []).map((row) => (
                <tr key={row.id}>
                  <td className="strong">{row.display_name}</td>
                  <td>{row.preferred_language}</td>
                  <td>{row.district ?? '—'}</td>
                  <td>{row.mobility}</td>
                  <td>{row.skill_count}</td>
                  <td>
                    <Chip tone={row.is_confirmed ? 'good' : 'warn'}>
                      {row.is_confirmed ? 'confirmed' : 'not confirmed'}
                    </Chip>
                  </td>
                  <td>
                    <Button
                      variant="secondary"
                      onClick={() => setSelected(selected === row.id ? null : row.id)}
                    >
                      {selected === row.id ? 'Close' : 'Review'}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {selected && detail.loading ? <Loading label="Loading extraction…" /> : null}

      {selected && detail.data ? (
        <Card>
          <h3>What the system extracted</h3>
          <p className="small muted">
            Review the AI's reading of each conversation turn before trusting the profile built from
            it.
          </p>
          {(detail.data.conversations as any[]).map((conversation) => (
            <div key={conversation.id} style={{ marginTop: 'var(--space-4)' }}>
              <div className="row" style={{ gap: 'var(--space-2)' }}>
                <Chip icon="💬">{conversation.channel}</Chip>
                <Chip icon="🌐">{conversation.language}</Chip>
                <Chip>{conversation.state}</Chip>
              </div>
              <div className="stack-sm" style={{ marginTop: 'var(--space-3)' }}>
                {(conversation.messages as any[])
                  .filter((message) => message.role === 'beneficiary')
                  .map((message) => (
                    <div
                      key={message.sequence}
                      style={{
                        padding: 'var(--space-3)',
                        background: 'var(--grey-050)',
                        borderRadius: 'var(--radius)',
                      }}
                    >
                      <p className="small strong" style={{ marginBottom: 4 }}>
                        &ldquo;{message.raw_text}&rdquo;
                      </p>
                      <div className="row tiny muted" style={{ gap: 'var(--space-3)' }}>
                        <span>language: {message.detected_language}</span>
                        {message.language_confidence !== null ? (
                          <span>confidence: {Math.round(message.language_confidence * 100)}%</span>
                        ) : null}
                        {message.asr_confidence !== null ? (
                          <span>ASR: {Math.round(message.asr_confidence * 100)}%</span>
                        ) : null}
                        {message.is_code_switched ? <span>code-switched</span> : null}
                        {message.needs_confirmation ? <span>asked to confirm</span> : null}
                      </div>
                      {message.extracted_entities?.skills?.length ? (
                        <ul className="tag-list" style={{ marginTop: 'var(--space-2)' }}>
                          {message.extracted_entities.skills.map((skill: any) => (
                            <li key={skill.code}>
                              <Chip tone="info" icon="◆" title={skill.evidence}>
                                {skill.name} ({skill.proficiency})
                              </Chip>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </Card>
      ) : null}

      {selected && recommendations.data ? (
        <Card>
          <h3>Recommendations made to this beneficiary</h3>
          <p className="small muted">
            Accept, edit or reject any of these. Every decision is recorded in the audit log with
            your name against it.
          </p>
          <div className="stack">
            {recommendations.data.recommendations.map((recommendation) => (
              <div
                key={recommendation.id}
                style={{
                  padding: 'var(--space-4)',
                  border: '1px solid var(--grey-200)',
                  borderRadius: 'var(--radius)',
                }}
              >
                <div className="row row--between">
                  <div>
                    <strong>
                      {recommendation.rank}. {recommendation.title}
                    </strong>
                    <p className="small muted" style={{ margin: 0 }}>
                      Match {Math.round(recommendation.match_score * 100)}% ·{' '}
                      {recommendation.distance_km !== null
                        ? `${Math.round(recommendation.distance_km)} km`
                        : 'distance unknown'}{' '}
                      · {recommendation.provider}
                    </p>
                  </div>
                  {recommendation.is_overridden ? (
                    <Chip tone={recommendation.override_action === 'reject' ? 'bad' : 'info'} icon="✎">
                      {recommendation.override_action}
                    </Chip>
                  ) : null}
                </div>

                <ul className="reason-list" style={{ marginTop: 'var(--space-3)' }}>
                  {recommendation.why_it_fits.slice(0, 3).map((reason, index) => (
                    <li key={index}>
                      <span className="reason-list__icon">✓</span>
                      <span className="small">{reason}</span>
                    </li>
                  ))}
                </ul>

                {overrideFor === recommendation.id ? (
                  <div style={{ marginTop: 'var(--space-3)' }}>
                    <label htmlFor={`note-${recommendation.id}`}>Reason (required, logged)</label>
                    <textarea
                      id={`note-${recommendation.id}`}
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                      rows={2}
                    />
                    <div className="row" style={{ marginTop: 'var(--space-3)' }}>
                      <Button
                        onClick={() => override.run(recommendation.id, 'accept')}
                        disabled={note.trim().length < 3}
                        loading={override.pending}
                      >
                        Accept
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => override.run(recommendation.id, 'edit')}
                        disabled={note.trim().length < 3}
                        loading={override.pending}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="danger"
                        onClick={() => override.run(recommendation.id, 'reject')}
                        disabled={note.trim().length < 3}
                        loading={override.pending}
                      >
                        Reject
                      </Button>
                      <Button variant="ghost" onClick={() => setOverrideFor(null)}>
                        Cancel
                      </Button>
                    </div>
                    {override.error ? (
                      <p className="small" style={{ color: 'var(--red-700)' }}>{override.error}</p>
                    ) : null}
                  </div>
                ) : (
                  <Button
                    variant="secondary"
                    onClick={() => setOverrideFor(recommendation.id)}
                    style={{ marginTop: 'var(--space-3)' }}
                  >
                    Review this recommendation
                  </Button>
                )}
              </div>
            ))}
          </div>
        </Card>
      ) : null}
    </div>
  )
}

function AuditTrail() {
  const [action, setAction] = useState('')
  const audit = useAsync(() => api.audit(action ? { action } : {}), [action])

  return (
    <div className="stack">
      <div className="row row--between">
        <h2 style={{ margin: 0 }}>Audit trail</h2>
        <select
          value={action}
          onChange={(event) => setAction(event.target.value)}
          style={{ maxWidth: 280 }}
          aria-label="Filter by action"
        >
          <option value="">All actions</option>
          <option value="recommendation.override">Recommendation overrides</option>
          <option value="recommendation.generated">Recommendations generated</option>
          <option value="opportunity.verified">Opportunity verified</option>
          <option value="opportunity.created">Opportunity created</option>
          <option value="opportunity.updated">Opportunity updated</option>
          <option value="profile.confirmed">Profile confirmed</option>
          <option value="pathway.selected">Pathway selected</option>
          <option value="auth.login.success">Sign in</option>
        </select>
      </div>

      {audit.loading ? <Loading /> : null}
      {audit.error ? <ErrorState message={audit.error} onRetry={audit.reload} /> : null}

      {audit.data && audit.data.length === 0 ? (
        <EmptyState icon="🗒️" title="No entries" description="Nothing matches this filter yet." />
      ) : null}

      {audit.data && audit.data.length > 0 ? (
        <Card className="card--flush">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Action</th>
                  <th>Who</th>
                  <th>Entity</th>
                  <th>Change</th>
                </tr>
              </thead>
              <tbody>
                {audit.data.map((entry) => (
                  <tr key={entry.id}>
                    <td className="nowrap tiny">{new Date(entry.created_at).toLocaleString()}</td>
                    <td className="nowrap"><Chip>{entry.action}</Chip></td>
                    <td className="tiny">
                      {entry.actor_email ?? 'system'}
                      <div className="muted">{entry.actor_role}</div>
                    </td>
                    <td className="tiny">
                      {entry.entity_type}
                      <div className="muted">{entry.entity_id?.slice(0, 8)}</div>
                    </td>
                    <td className="tiny" style={{ maxWidth: 360 }}>
                      {entry.summary}
                      {entry.old_value || entry.new_value ? (
                        <details>
                          <summary className="muted" style={{ cursor: 'pointer' }}>
                            before / after
                          </summary>
                          <pre
                            style={{
                              whiteSpace: 'pre-wrap',
                              fontSize: '0.72rem',
                              background: 'var(--grey-050)',
                              padding: 8,
                              borderRadius: 6,
                              margin: '6px 0 0',
                            }}
                          >
{JSON.stringify({ before: entry.old_value, after: entry.new_value }, null, 2)}
                          </pre>
                        </details>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}
    </div>
  )
}

export function AdminDashboard() {
  const { isAdmin, user } = useApp()
  const [tab, setTab] = useState<Tab>('overview')

  if (!isAdmin) {
    return (
      <Layout wide>
        <EmptyState
          icon="🔒"
          title="Staff access only"
          description="Sign in with an administrator or counsellor account to open this console."
        />
      </Layout>
    )
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'opportunities', label: 'Opportunities' },
    { key: 'beneficiaries', label: 'Beneficiaries & AI review' },
    { key: 'audit', label: 'Audit trail' },
  ]

  return (
    <Layout wide>
      <div className="stack">
        <div className="row row--between">
          <h1 style={{ margin: 0 }}>Administration</h1>
          <span className="small muted">Signed in as {user?.email}</span>
        </div>

        <div className="tabs" role="tablist">
          {tabs.map((entry) => (
            <button
              key={entry.key}
              role="tab"
              aria-selected={tab === entry.key}
              className="tab"
              onClick={() => setTab(entry.key)}
            >
              {entry.label}
            </button>
          ))}
        </div>

        {tab === 'overview' ? <Overview /> : null}
        {tab === 'opportunities' ? <Opportunities /> : null}
        {tab === 'beneficiaries' ? <Beneficiaries /> : null}
        {tab === 'audit' ? <AuditTrail /> : null}
      </div>
    </Layout>
  )
}
