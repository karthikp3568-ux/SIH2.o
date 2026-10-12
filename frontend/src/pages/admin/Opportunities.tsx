/**
 * Opportunity catalogue and verification.
 *
 * "Verification" is the same table filtered to what needs a human: stale,
 * unverified or about to expire. Verifying records the reviewer and extends
 * validity; importing never verifies.
 */

import { useMemo, useState } from 'react'

import { api } from '../../api/client'
import type { Opportunity } from '../../api/types'
import { Icon, OPPORTUNITY_TYPE } from '../../components/Icon'
import {
  Button,
  EmptyState,
  ErrorState,
  Loading,
  Notice,
  StatusChip,
  Toast,
  TrustBadge,
  formatDate,
  opportunityState,
} from '../../components/ui'
import type { OpportunityState } from '../../components/ui'
import { useAction, useAsync } from '../../hooks/useAsync'
import { educationLabel } from '../../lib/labels'
import { OpportunityEditor } from './OpportunityEditor'

type Filter = 'all' | 'attention' | OpportunityState

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'attention', label: 'Needs attention' },
  { key: 'active', label: 'Active' },
  { key: 'expiring', label: 'Expiring' },
  { key: 'stale', label: 'Stale' },
  { key: 'unverified', label: 'Unverified' },
  { key: 'inactive', label: 'Inactive' },
]

const NEEDS_ATTENTION: OpportunityState[] = ['expiring', 'stale', 'unverified']

export function Opportunities({ mode }: { mode: 'all' | 'verification' }) {
  const [filter, setFilter] = useState<Filter>(mode === 'verification' ? 'attention' : 'all')
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<Opportunity | 'new' | null>(null)
  const [importReport, setImportReport] = useState<Record<string, any> | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const list = useAsync(() => api.adminOpportunities({ limit: '200', ...(query ? { q: query } : {}) }), [query])

  const rows = useMemo(
    () => (list.data?.items ?? []).map((o) => ({ o, state: opportunityState(o) })),
    [list.data],
  )
  const counts = useMemo(() => {
    const map = new Map<Filter, number>([['all', rows.length]])
    for (const { state } of rows) {
      map.set(state, (map.get(state) ?? 0) + 1)
      if (NEEDS_ATTENTION.includes(state)) map.set('attention', (map.get('attention') ?? 0) + 1)
    }
    return map
  }, [rows])
  const visible = rows.filter(({ state }) =>
    filter === 'all' ? true : filter === 'attention' ? NEEDS_ATTENTION.includes(state) : state === filter,
  )

  const replace = (updated: Opportunity) =>
    list.setData(list.data ? { ...list.data, items: list.data.items.map((o) => (o.id === updated.id ? updated : o)) } : null)

  const verify = useAction(async (o: Opportunity) => {
    setBusyId(o.id)
    const updated = await api.verifyOpportunity(o.id, {
      verification_status: 'admin_verified',
      note: 'Checked against the source',
      extend_valid_days: 90,
    })
    replace(updated)
    setBusyId(null)
    setToast(`Verified “${o.title}” — valid for 90 more days.`)
    return updated
  })

  const deactivate = useAction(async (o: Opportunity) => {
    setBusyId(o.id)
    await api.deleteOpportunity(o.id)
    list.reload()
    setBusyId(null)
    setToast(`Deactivated “${o.title}”. It will no longer be recommended.`)
    return true
  })

  const doImport = useAction(async (file: File, dryRun: boolean) => {
    const report = await api.importOpportunities(file, dryRun)
    setImportReport({ ...report, file })
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
          setToast('Saved.')
        }}
      />
    )
  }

  return (
    <div className="admin-stack">
      {mode === 'verification' ? (
        <Notice tone="info" title="Only verified, current listings are recommended">
          <p className="small" style={{ margin: 0 }}>
            Check each listing against its source, then verify it. Listings not checked for 90 days are marked stale;
            after a year they are excluded from matching automatically.
          </p>
        </Notice>
      ) : null}

      <div className="toolbar">
        <div className="toolbar__search">
          <Icon name="search" size={17} />
          <label htmlFor="opp-search" className="visually-hidden">
            Search listings
          </label>
          <input id="opp-search" type="search" placeholder="Search title or provider" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="row row--tight">
          <Button variant="ghost" icon="refresh" onClick={list.reload}>
            Refresh
          </Button>
          <label className="btn btn--secondary" htmlFor="csv-import">
            <Icon name="file" size={17} /> Import CSV
            <input
              id="csv-import"
              type="file"
              accept=".csv,text/csv"
              className="visually-hidden"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) void doImport.run(file, true)
                event.target.value = ''
              }}
            />
          </label>
          <Button icon="plus" onClick={() => setEditing('new')}>
            Add opportunity
          </Button>
        </div>
      </div>

      <div className="filter-chips" role="group" aria-label="Filter by status">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
            {f.label}
            <span>{counts.get(f.key) ?? 0}</span>
          </button>
        ))}
      </div>

      {importReport ? (
        <Notice tone={importReport.errors?.length ? 'warn' : 'success'} title={importReport.dry_run ? 'Dry run — nothing saved yet' : 'Import complete'}>
          <p className="small" style={{ marginBottom: 8 }}>
            {importReport.rows_read} rows read · {importReport.created} to create · {importReport.updated} to update · {importReport.skipped} skipped
          </p>
          {(importReport.errors ?? []).length > 0 ? (
            <ul className="small" style={{ margin: '0 0 8px', paddingLeft: '1.2rem' }}>
              {(importReport.errors as { row: number; errors: string[] }[]).slice(0, 6).map((e) => (
                <li key={e.row}>
                  Row {e.row}: {e.errors.join('; ')}
                </li>
              ))}
            </ul>
          ) : null}
          <div className="row row--tight">
            {importReport.dry_run ? (
              <Button size="sm" onClick={() => doImport.run(importReport.file, false)} loading={doImport.pending}>
                Import for real
              </Button>
            ) : null}
            <Button size="sm" variant="ghost" onClick={() => setImportReport(null)}>
              Dismiss
            </Button>
          </div>
          <p className="tiny muted" style={{ margin: '8px 0 0' }}>
            Imported records arrive as drafts and unverified — importing is not verifying.
          </p>
        </Notice>
      ) : null}

      {list.loading && !list.data ? <Loading label="Loading listings…" /> : null}
      {list.error ? <ErrorState message="We couldn’t load listings." onRetry={list.reload} /> : null}
      {verify.error || deactivate.error ? <ErrorState message="That action didn’t go through. Please try again." /> : null}

      {list.data && visible.length === 0 ? (
        <EmptyState
          icon={filter === 'attention' ? 'checkCircle' : 'search'}
          title={filter === 'attention' ? 'Everything is verified and current' : 'No listings match'}
          description={filter === 'attention' ? 'Nothing needs a human right now.' : 'Try a different filter or search.'}
        />
      ) : null}

      {visible.length > 0 ? (
        <div className="panel panel--flush">
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Opportunity</th>
                  <th>Location</th>
                  <th>Eligibility</th>
                  <th>Status</th>
                  <th>Last verified</th>
                  <th>Valid until</th>
                  <th>
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {visible.map(({ o, state }) => {
                  const type = OPPORTUNITY_TYPE[o.opportunity_type] ?? OPPORTUNITY_TYPE.training
                  return (
                    <tr key={o.id}>
                      <td>
                        <div className="cell-title">
                          <span className="icon-tile icon-tile--sm">
                            <Icon name={type.icon} size={16} />
                          </span>
                          <div>
                            <strong>{o.title}</strong>
                            <div className="tiny muted">
                              {o.provider} · {type.label}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="small">{o.location_label ?? o.district ?? '—'}</td>
                      <td className="small">
                        {o.education_required ? educationLabel(o.education_required) : 'Open'}
                        {o.min_age || o.max_age ? <div className="tiny muted">Age {o.min_age ?? '—'}–{o.max_age ?? '—'}</div> : null}
                      </td>
                      <td>
                        <StatusChip state={state} />
                      </td>
                      <td>
                        <TrustBadge verificationStatus={o.verification_status} lastVerifiedAt={o.last_verified_at} />
                      </td>
                      <td className="small nowrap">{formatDate(o.valid_until)}</td>
                      <td>
                        <div className="row row--tight" style={{ flexWrap: 'nowrap' }}>
                          <Button size="sm" variant="success" icon="shield" onClick={() => verify.run(o)} loading={busyId === o.id && verify.pending}>
                            Verify
                          </Button>
                          <Button size="sm" variant="secondary" icon="edit" onClick={() => setEditing(o)} aria-label={`Edit ${o.title}`}>
                            Edit
                          </Button>
                          {o.status === 'active' ? (
                            <Button
                              size="sm"
                              variant="danger"
                              icon="power"
                              onClick={() => deactivate.run(o)}
                              loading={busyId === o.id && deactivate.pending}
                              aria-label={`Deactivate ${o.title}`}
                            />
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  )
}
