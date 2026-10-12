/**
 * AI review — the human check on every recommendation.
 *
 * Staff see what the person said, the profile and skill graph built from it,
 * and the factors behind each recommendation, then accept, edit or reject it.
 * A reason is mandatory and is written to the audit trail with the reviewer's
 * name; an edit can replace the next step the beneficiary will see.
 */

import { useEffect, useState } from 'react'

import { api } from '../../api/client'
import type { Recommendation } from '../../api/types'
import { Icon, OPPORTUNITY_TYPE } from '../../components/Icon'
import { SkillGraph } from '../../components/SkillGraph'
import { Button, Chip, EmptyState, ErrorState, Loading, VerificationChip } from '../../components/ui'
import type { AsyncState } from '../../hooks/useAsync'
import { useAction, useAsync } from '../../hooks/useAsync'
import type { ReviewItem, ReviewQueueData } from '../../lib/adminData'
import { LANGUAGE_NAME, educationLabel, goalLabel, mobilityLabel } from '../../lib/labels'

type Decision = 'accept' | 'edit' | 'reject'

function RecReview({ rec, onDone }: { rec: Recommendation; onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [decision, setDecision] = useState<Decision | null>(null)
  const [note, setNote] = useState('')
  const [nextStep, setNextStep] = useState(rec.next_step)
  const explanation = useAsync(() => (open ? api.explanation(rec.id) : Promise.resolve(null)), [open, rec.id])
  const type = OPPORTUNITY_TYPE[rec.opportunity_type] ?? OPPORTUNITY_TYPE.training

  const submit = useAction(async () => {
    if (!decision) return undefined
    await api.overrideRecommendation(rec.id, {
      action: decision,
      note: note.trim(),
      revised_next_step: decision === 'edit' && nextStep.trim() !== rec.next_step ? nextStep.trim() : undefined,
    })
    setDecision(null)
    setNote('')
    onDone()
    return true
  })

  return (
    <article className={`review-rec ${rec.is_overridden ? 'is-reviewed' : ''}`}>
      <header className="review-rec__head">
        <span className="review-rec__rank">{rec.rank}</span>
        <span className="icon-tile icon-tile--sm icon-tile--blue">
          <Icon name={type.icon} size={17} />
        </span>
        <div className="grow">
          <strong>{rec.title}</strong>
          <div className="tiny muted">
            {rec.provider} · {rec.distance_km !== null ? `${rec.distance_km.toFixed(1)} km` : 'distance unknown'} · score{' '}
            <span className="mono">{rec.match_score.toFixed(3)}</span>
          </div>
        </div>
        {rec.is_overridden ? (
          <span className={`decision decision--${rec.override_action}`}>
            <Icon name={rec.override_action === 'reject' ? 'x' : rec.override_action === 'edit' ? 'edit' : 'check'} size={13} strokeWidth={3} />
            {rec.override_action === 'accept' ? 'Accepted' : rec.override_action === 'edit' ? 'Edited' : 'Rejected'}
          </span>
        ) : (
          <span className="decision decision--pending">
            <Icon name="clock" size={13} /> Awaiting review
          </span>
        )}
      </header>

      <div className="review-rec__cols">
        <div>
          <div className="review-rec__label">Why it was ranked</div>
          <ul className="tag-list">
            {rec.why_it_fits.slice(0, 5).map((reason) => (
              <li key={reason}>
                <Chip tone="good" icon="check">
                  {reason.length > 48 ? `${reason.slice(0, 46)}…` : reason}
                </Chip>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="review-rec__label">Skill gap ({rec.skill_gap})</div>
          <ul className="tag-list">
            {rec.missing_competencies.map((c) => (
              <li key={c.code}>
                <span className="need-chip" title={c.nos_code ?? undefined}>
                  {c.name}
                </span>
              </li>
            ))}
            {rec.missing_competencies.length === 0 ? <li className="small muted">None</li> : null}
          </ul>
        </div>
      </div>

      <button type="button" className="review-rec__toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <Icon name={open ? 'chevronDown' : 'chevronRight'} size={16} /> Recommendation factors
      </button>
      {open ? (
        explanation.loading ? (
          <Loading label="Loading factors…" />
        ) : explanation.data ? (
          <table className="factor-table">
            <thead>
              <tr>
                <th>Factor</th>
                <th>Score</th>
                <th>Weight</th>
                <th>Contribution</th>
              </tr>
            </thead>
            <tbody>
              {explanation.data.factors.map((f) => (
                <tr key={f.code}>
                  <td>{f.label}</td>
                  <td>
                    <span className="factor-table__bar">
                      <span style={{ width: `${f.score * 100}%` }} />
                    </span>
                    <span className="mono">{f.score.toFixed(2)}</span>
                  </td>
                  <td className="mono">{f.weight.toFixed(2)}</td>
                  <td className="mono">{f.contribution.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null
      ) : null}

      {!rec.is_overridden ? (
        <div className="review-rec__decide">
          <div className="decide-buttons" role="group" aria-label="Decision">
            {(['accept', 'edit', 'reject'] as Decision[]).map((d) => (
              <button key={d} type="button" className={`decide decide--${d}`} aria-pressed={decision === d} onClick={() => setDecision(decision === d ? null : d)}>
                <Icon name={d === 'accept' ? 'check' : d === 'edit' ? 'edit' : 'x'} size={15} strokeWidth={2.6} />
                {d === 'accept' ? 'Accept' : d === 'edit' ? 'Edit' : 'Reject'}
              </button>
            ))}
          </div>
          {decision ? (
            <div className="decide-form enter">
              {decision === 'edit' ? (
                <div className="field">
                  <label htmlFor={`next-${rec.id}`}>Next step the beneficiary will see</label>
                  <textarea id={`next-${rec.id}`} rows={2} value={nextStep} onChange={(e) => setNextStep(e.target.value)} />
                </div>
              ) : null}
              <div className="field">
                <label htmlFor={`note-${rec.id}`}>
                  Reason <span className="muted">(required — recorded in the audit trail)</span>
                </label>
                <textarea id={`note-${rec.id}`} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
              </div>
              <div className="row">
                <Button
                  variant={decision === 'reject' ? 'danger' : decision === 'accept' ? 'success' : 'primary'}
                  onClick={() => submit.run()}
                  disabled={note.trim().length < 3}
                  loading={submit.pending}
                >
                  Record {decision}
                </Button>
                <Button variant="ghost" onClick={() => setDecision(null)}>
                  Cancel
                </Button>
              </div>
              {submit.error ? <p className="small" style={{ color: 'var(--red-700)' }}>{submit.error}</p> : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  )
}

function ReviewPanel({ item, onChanged }: { item: ReviewItem; onChanged: () => void }) {
  const id = item.beneficiary.id
  const detail = useAsync(async () => {
    const [extraction, graph] = await Promise.all([api.adminExtraction(id), api.skillGraph(id).catch(() => null)])
    return { extraction, graph }
  }, [id])
  const [showGraph, setShowGraph] = useState(true)

  if (detail.loading) return <Loading label="Loading this beneficiary…" />
  if (detail.error || !detail.data) return <ErrorState message="We couldn’t load this beneficiary." onRetry={detail.reload} />

  const profile = detail.data.extraction.profile as any
  const said = (detail.data.extraction.conversations as any[])
    .flatMap((c) => c.messages as any[])
    .filter((m) => m.role === 'beneficiary')

  return (
    <div className="review-panel">
      <header className="review-person">
        <span className="queue-list__avatar queue-list__avatar--lg">{item.beneficiary.display_name.charAt(0)}</span>
        <div className="grow">
          <h2 style={{ margin: 0 }}>{item.beneficiary.display_name}</h2>
          <div className="small muted">
            {item.beneficiary.district ?? 'District not set'} · {LANGUAGE_NAME[item.beneficiary.preferred_language] ?? item.beneficiary.preferred_language} ·
            Travel: {mobilityLabel(item.beneficiary.mobility)}
          </div>
        </div>
        <span className="decision decision--pending">{item.pending.length} awaiting</span>
      </header>

      <div className="review-grid">
        <section className="panel">
          <h3 className="panel__sub" style={{ marginTop: 0 }}>What they said</h3>
          <ul className="said-list">
            {said.map((m) => (
              <li key={m.sequence}>
                <p>“{m.raw_text}”</p>
                <div className="tiny muted">
                  {m.detected_language ? `Language ${m.detected_language}` : ''}
                  {m.language_confidence != null ? ` (${Math.round(m.language_confidence * 100)}%)` : ''}
                  {m.asr_confidence != null ? ` · ASR ${Math.round(m.asr_confidence * 100)}%` : ' · typed'}
                  {m.is_code_switched ? ' · code-switched' : ''}
                </div>
              </li>
            ))}
          </ul>
        </section>
        <section className="panel">
          <h3 className="panel__sub" style={{ marginTop: 0 }}>Confirmed profile</h3>
          <dl className="profile-dl">
            <div>
              <dt>Education</dt>
              <dd>{profile.education ? educationLabel(profile.education.level) : '—'}</dd>
            </div>
            <div>
              <dt>Goal</dt>
              <dd>{(profile.goals ?? []).map((g: any) => goalLabel(g.goal_type)).join(', ') || '—'}</dd>
            </div>
            <div>
              <dt>Skills</dt>
              <dd>
                <ul className="tag-list">
                  {(profile.skills ?? []).map((s: any) => (
                    <li key={s.id} className="row row--tight">
                      <Chip>{s.name}</Chip>
                      <VerificationChip status={s.verification_status} />
                    </li>
                  ))}
                </ul>
              </dd>
            </div>
          </dl>
        </section>
      </div>

      {detail.data.graph ? (
        <section className="panel">
          <header className="panel__head">
            <h3 className="panel__sub" style={{ margin: 0 }}>Skill graph</h3>
            <Button variant="ghost" size="sm" onClick={() => setShowGraph((v) => !v)}>
              {showGraph ? 'Hide' : 'Show'}
            </Button>
          </header>
          {showGraph ? <SkillGraph graph={detail.data.graph} name={item.beneficiary.display_name} /> : null}
        </section>
      ) : null}

      <h3 className="review-recs-title">Recommendations</h3>
      <div className="review-recs">
        {item.run.recommendations.map((rec) => (
          <RecReview key={rec.id} rec={rec} onDone={onChanged} />
        ))}
      </div>
    </div>
  )
}

export function ReviewQueue({ queue }: { queue: AsyncState<ReviewQueueData | null> }) {
  const [selected, setSelected] = useState<string | null>(null)
  const items = queue.data?.items ?? []

  useEffect(() => {
    if (!selected && items.length > 0) setSelected((items.find((i) => i.pending.length > 0) ?? items[0]).beneficiary.id)
  }, [items, selected])

  if (queue.loading && !queue.data) return <Loading label="Loading the review queue…" />
  if (queue.error) return <ErrorState message="We couldn’t load the review queue." onRetry={queue.reload} />
  if (items.length === 0) {
    return <EmptyState icon="inbox" title="Nothing to review" description="Recommendations appear here once a beneficiary confirms their profile." />
  }

  const current = items.find((i) => i.beneficiary.id === selected) ?? null

  return (
    <div className="review-layout">
      <nav className="review-nav" aria-label="Beneficiaries with recommendations">
        <div className="eyebrow" style={{ padding: '0 var(--space-2) var(--space-2)' }}>
          {queue.data?.pendingCount ?? 0} awaiting review
        </div>
        {items.map((item) => (
          <button
            key={item.beneficiary.id}
            type="button"
            className="review-nav__item"
            aria-current={item.beneficiary.id === selected}
            onClick={() => setSelected(item.beneficiary.id)}
          >
            <span className="queue-list__avatar">{item.beneficiary.display_name.charAt(0)}</span>
            <span className="grow">
              <strong>{item.beneficiary.display_name}</strong>
              <span className="tiny muted">{item.run.recommendations.length} recommendations</span>
            </span>
            {item.pending.length > 0 ? (
              <span className="queue-list__count">{item.pending.length}</span>
            ) : (
              <Icon name="checkCircle" size={18} className="review-nav__done" />
            )}
          </button>
        ))}
      </nav>
      {current ? <ReviewPanel key={current.beneficiary.id} item={current} onChanged={queue.reload} /> : null}
    </div>
  )
}
