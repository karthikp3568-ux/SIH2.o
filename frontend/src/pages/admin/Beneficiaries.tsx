/** Beneficiaries, with the AI's turn-by-turn extraction one click away. */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../../api/client'
import { Icon } from '../../components/Icon'
import { Chip, Drawer, EmptyState, ErrorState, Loading } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import type { BeneficiaryRow } from '../../lib/adminData'
import { LANGUAGE_NAME, goalLabel, mobilityLabel } from '../../lib/labels'

function Extraction({ id }: { id: string }) {
  const detail = useAsync(() => api.adminExtraction(id), [id])
  if (detail.loading) return <Loading label="Loading what the system extracted…" />
  if (detail.error || !detail.data) return <ErrorState message="We couldn’t load the extraction." />
  const conversations = detail.data.conversations as any[]
  if (conversations.length === 0) return <p className="muted">No conversations yet.</p>

  return (
    <div className="admin-stack">
      <p className="small muted" style={{ margin: 0 }}>
        Each thing the beneficiary said, and what the system extracted from it. Check this before trusting the profile built from it.
      </p>
      {conversations.map((c) => (
        <div key={c.id} className="admin-stack" style={{ gap: 'var(--space-3)' }}>
          <div className="row row--tight">
            <Chip icon={c.channel === 'web_voice' ? 'mic' : 'keyboard'}>{c.channel === 'web_voice' ? 'Voice' : 'Typed'}</Chip>
            <Chip icon="globe">{LANGUAGE_NAME[c.language] ?? c.language}</Chip>
            <Chip tone={c.state === 'confirmed' ? 'good' : 'warn'}>{c.state.replace(/_/g, ' ')}</Chip>
          </div>
          {(c.messages as any[])
            .filter((m) => m.role === 'beneficiary')
            .map((m) => (
              <div key={m.sequence} className="said-card">
                <p>“{m.raw_text}”</p>
                <div className="tiny muted">
                  {m.detected_language ? `Language ${m.detected_language}` : ''}
                  {m.language_confidence != null ? ` · ${Math.round(m.language_confidence * 100)}%` : ''}
                  {m.asr_confidence != null ? ` · ASR ${Math.round(m.asr_confidence * 100)}%` : ''}
                  {m.is_code_switched ? ' · code-switched' : ''}
                  {m.needs_confirmation ? ' · asked to confirm' : ''}
                </div>
                {m.extracted_entities?.skills?.length ? (
                  <ul className="tag-list" style={{ marginTop: 8 }}>
                    {m.extracted_entities.skills.map((s: any) => (
                      <li key={s.code}>
                        <Chip tone="info" icon="plus" title={s.evidence}>
                          {s.name} · {s.proficiency}
                        </Chip>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ))}
        </div>
      ))}
    </div>
  )
}

export function Beneficiaries() {
  const list = useAsync(() => api.adminBeneficiaries() as Promise<BeneficiaryRow[]>, [])
  const [open, setOpen] = useState<BeneficiaryRow | null>(null)

  if (list.loading) return <Loading label="Loading beneficiaries…" />
  if (list.error) return <ErrorState message="We couldn’t load beneficiaries." onRetry={list.reload} />
  const rows = list.data ?? []
  if (rows.length === 0) return <EmptyState icon="users" title="No beneficiaries yet" description="People appear here after their first conversation." />

  return (
    <div className="admin-stack">
      <div className="panel panel--flush">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Beneficiary</th>
                <th>Language</th>
                <th>District</th>
                <th>Travel</th>
                <th>Goal</th>
                <th>Skills</th>
                <th>Profile</th>
                <th>
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((b) => (
                <tr key={b.id}>
                  <td>
                    <div className="cell-title">
                      <span className="queue-list__avatar">{b.display_name.charAt(0)}</span>
                      <strong>{b.display_name}</strong>
                    </div>
                  </td>
                  <td className="small">{LANGUAGE_NAME[b.preferred_language] ?? b.preferred_language}</td>
                  <td className="small">{b.district ?? '—'}</td>
                  <td className="small">{mobilityLabel(b.mobility)}</td>
                  <td className="small">{b.goals.map(goalLabel).join(', ') || '—'}</td>
                  <td className="small">{b.skill_count}</td>
                  <td>
                    {b.is_confirmed ? (
                      <Chip tone="good" icon="check">
                        Confirmed
                      </Chip>
                    ) : (
                      <Chip tone="warn" icon="clock">
                        Not confirmed
                      </Chip>
                    )}
                  </td>
                  <td>
                    <button type="button" className="btn btn--secondary btn--sm" onClick={() => setOpen(b)}>
                      <Icon name="eye" size={15} /> Extraction
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <p className="small muted">
        To accept, edit or reject what was recommended to someone, use the <Link to="/admin/recommendations">AI review queue</Link>.
      </p>

      <Drawer open={open !== null} onClose={() => setOpen(null)} eyebrow="What the AI extracted" title={open?.display_name ?? ''}>
        {open ? <Extraction id={open.id} /> : null}
      </Drawer>
    </div>
  )
}
