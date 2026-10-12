/** Every consequential action, who took it, and what changed. */

import { useState } from 'react'

import { api } from '../../api/client'
import { EmptyState, ErrorState, Loading } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'

const ACTIONS: { value: string; label: string }[] = [
  { value: '', label: 'All actions' },
  { value: 'recommendation.override', label: 'Recommendation reviews' },
  { value: 'recommendation.generated', label: 'Recommendations generated' },
  { value: 'opportunity.verified', label: 'Opportunity verified' },
  { value: 'opportunity.created', label: 'Opportunity created' },
  { value: 'opportunity.updated', label: 'Opportunity updated' },
  { value: 'profile.confirmed', label: 'Profile confirmed' },
  { value: 'pathway.selected', label: 'Pathway selected' },
  { value: 'auth.login.success', label: 'Sign in' },
]

function tone(action: string): string {
  if (action.startsWith('recommendation.override')) return 'amber'
  if (action.includes('verified') || action.includes('confirmed')) return 'teal'
  if (action.startsWith('auth')) return 'neutral'
  return 'blue'
}

export function AuditTrail() {
  const [action, setAction] = useState('')
  const audit = useAsync(() => api.audit(action ? { action } : {}), [action])

  return (
    <div className="admin-stack">
      <div className="toolbar">
        <p className="small muted" style={{ margin: 0, maxWidth: '60ch' }}>
          Append-only. Reviews of AI recommendations, verifications and profile confirmations are all recorded with the person who made them.
        </p>
        <select value={action} onChange={(e) => setAction(e.target.value)} aria-label="Filter by action" style={{ maxWidth: 280 }}>
          {ACTIONS.map((a) => (
            <option key={a.value} value={a.value}>
              {a.label}
            </option>
          ))}
        </select>
      </div>

      {audit.loading ? <Loading label="Loading the audit trail…" /> : null}
      {audit.error ? <ErrorState message="We couldn’t load the audit trail." onRetry={audit.reload} /> : null}
      {audit.data && audit.data.length === 0 ? <EmptyState icon="file" title="No entries" description="Nothing matches this filter yet." /> : null}

      {audit.data && audit.data.length > 0 ? (
        <div className="panel panel--flush">
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Action</th>
                  <th>Who</th>
                  <th>What changed</th>
                </tr>
              </thead>
              <tbody>
                {audit.data.map((entry) => (
                  <tr key={entry.id}>
                    <td className="tiny nowrap">{new Date(entry.created_at).toLocaleString()}</td>
                    <td>
                      <span className={`audit-action audit-action--${tone(entry.action)}`}>{entry.action}</span>
                    </td>
                    <td className="small">
                      {entry.actor_email ?? 'system'}
                      <div className="tiny muted">{entry.actor_role}</div>
                    </td>
                    <td className="small" style={{ maxWidth: 420 }}>
                      {entry.summary}
                      {entry.old_value || entry.new_value ? (
                        <details className="audit-diff">
                          <summary>Before / after</summary>
                          <pre>{JSON.stringify({ before: entry.old_value, after: entry.new_value }, null, 2)}</pre>
                        </details>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  )
}
