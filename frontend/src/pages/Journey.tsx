/**
 * My Journey — outcome tracking.
 *
 * Objective milestones (enrolled, completed, working) and subjective feedback
 * (was it helpful, and if not why) are recorded separately, mirroring the
 * backend: what happened and how it felt are different facts, and both feed
 * the outcome learning loop.
 */

import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import type { Outcome } from '../api/types'
import { FlowSteps } from '../components/FlowSteps'
import { Icon } from '../components/Icon'
import type { IconName } from '../components/Icon'
import { Layout } from '../components/Layout'
import { Button, EmptyState, ErrorState, Loading, formatDate } from '../components/ui'
import { useAction, useAsync } from '../hooks/useAsync'
import { OUTCOME_ACTION, OUTCOME_WORD } from '../lib/labels'

const FORWARD = ['enrolled', 'attending', 'completed', 'employed', 'self_employed']
const STOPPED = ['dropped_out', 'rejected', 'changed_pathway', 'opportunity_inactive']

interface Milestone {
  key: string
  title: string
  doneTitle: string
  icon: IconName
  at: string | null
}

function milestones(outcome: Outcome, confirmedAt: string | null): Milestone[] {
  const livelihood = outcome.status === 'self_employed' ? 'Running your own work' : 'Working'
  return [
    { key: 'profile', title: 'Profile', doneTitle: 'Profile completed', icon: 'user', at: confirmedAt },
    { key: 'selected', title: 'Choose a pathway', doneTitle: 'Pathway chosen', icon: 'route', at: outcome.selected_at },
    { key: 'enrolled', title: 'Enrol', doneTitle: 'Enrolled', icon: 'edit', at: outcome.enrolled_at },
    { key: 'attending', title: 'Training', doneTitle: 'Training in progress', icon: 'book', at: outcome.started_at },
    { key: 'completed', title: 'Complete the training', doneTitle: 'Training completed', icon: 'cap', at: outcome.completed_at },
    { key: 'livelihood', title: 'Livelihood', doneTitle: livelihood, icon: 'sprout', at: outcome.employment_at },
  ]
}

/** How many milestones are finished for a status. */
function doneCount(status: string): number {
  const order: Record<string, number> = {
    recommended: 1,
    selected: 2,
    enrolled: 3,
    attending: 4,
    completed: 5,
    employed: 6,
    self_employed: 6,
  }
  return order[status] ?? 2
}

const FACES: { rating: number; useful: boolean | null; icon: IconName; label: string }[] = [
  { rating: 5, useful: true, icon: 'smile', label: 'Helpful' },
  { rating: 3, useful: null, icon: 'meh', label: 'Okay' },
  { rating: 1, useful: false, icon: 'frown', label: 'Not useful' },
]

function Feedback({ outcome }: { outcome: Outcome }) {
  const [face, setFace] = useState<number | null>(null)
  const [reason, setReason] = useState<string | null>(null)
  const [comment, setComment] = useState('')
  const [sent, setSent] = useState(false)
  const reasons = useAsync(() => api.feedbackReasons(), [])
  const chosen = FACES.find((f) => f.rating === face)

  const submit = useAction(async () => {
    await api.feedback({
      outcome_id: outcome.id,
      recommendation_id: outcome.recommendation_id,
      opportunity_id: outcome.opportunity_id,
      feedback_type: 'pathway_experience',
      was_useful: chosen?.useful ?? null,
      rating: chosen?.rating,
      rejection_reason: reason ?? undefined,
      comment: comment.trim() || undefined,
    })
    setSent(true)
    return true
  })

  if (sent) {
    return (
      <div className="feedback feedback--sent enter">
        <span className="icon-tile icon-tile--teal">
          <Icon name="checkCircle" size={22} />
        </span>
        <div>
          <strong>Thank you.</strong>
          <p className="small muted" style={{ margin: 0 }}>
            This shapes the pathways we suggest to people like you.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="feedback">
      <h3>How was this pathway?</h3>
      <div className="faces" role="radiogroup" aria-label="How was this pathway">
        {FACES.map((f) => (
          <button
            key={f.rating}
            type="button"
            role="radio"
            aria-checked={face === f.rating}
            className={`face face--${f.icon}`}
            onClick={() => {
              setFace(f.rating)
              if (f.useful) setReason(null)
            }}
          >
            <Icon name={f.icon} size={30} strokeWidth={1.8} />
            {f.label}
          </button>
        ))}
      </div>

      {face !== null && face < 5 ? (
        <div className="enter">
          <p className="feedback__q">What caused the problem?</p>
          <div className="reason-chips">
            {(reasons.data ?? []).map((r) => (
              <button key={r.code} type="button" className="option" aria-pressed={reason === r.code} onClick={() => setReason(reason === r.code ? null : r.code)}>
                {r.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {face !== null ? (
        <div className="enter" style={{ marginTop: 'var(--space-4)' }}>
          <label htmlFor="fb-comment" className="small">
            Anything else? <span className="muted">(optional)</span>
          </label>
          <textarea id="fb-comment" rows={2} value={comment} onChange={(event) => setComment(event.target.value)} />
          <Button style={{ marginTop: 'var(--space-3)' }} icon="send" onClick={() => submit.run()} loading={submit.pending}>
            Send feedback
          </Button>
          {submit.error ? (
            <p className="small" role="alert" style={{ color: 'var(--red-700)' }}>
              We couldn’t send that. Please try again.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export function Journey() {
  const navigate = useNavigate()
  const location = useLocation()
  const justChose = Boolean((location.state as { justChose?: boolean } | null)?.justChose)
  const data = useAsync(async () => {
    const [outcomes, profile] = await Promise.all([api.outcomes(), api.profile().catch(() => null)])
    return { outcomes, profile }
  }, [])
  const [justDone, setJustDone] = useState<number | null>(justChose ? 1 : null)
  const [income, setIncome] = useState('')
  const [showStop, setShowStop] = useState(false)

  const advance = useAction(async (outcome: Outcome, status: string) => {
    const before = doneCount(outcome.status)
    const updated = await api.updateOutcome(outcome.id, {
      status,
      monthly_income_inr: (status === 'employed' || status === 'self_employed') && income ? Number(income) : undefined,
    })
    data.setData(data.data ? { ...data.data, outcomes: data.data.outcomes.map((o) => (o.id === updated.id ? updated : o)) } : null)
    setJustDone(FORWARD.includes(status) ? doneCount(status) - 1 : before)
    setShowStop(false)
    return updated
  })

  if (data.loading) {
    return (
      <Layout>
        <Loading label="Opening your journey…" />
      </Layout>
    )
  }
  if (data.error || !data.data) {
    return (
      <Layout>
        <ErrorState message="We couldn’t open your journey right now." onRetry={data.reload} />
      </Layout>
    )
  }

  const { outcomes, profile } = data.data
  const active = outcomes.find((o) => o.is_active) ?? outcomes[0]

  if (!active) {
    return (
      <Layout>
        <FlowSteps current="journey" />
        <EmptyState
          icon="flag"
          title="You haven’t chosen a pathway yet"
          description="Pick one of your pathways and we’ll walk with you from training to a livelihood."
          action={
            <Button iconRight="arrowRight" onClick={() => navigate('/pathways')}>
              See my pathways
            </Button>
          }
        />
      </Layout>
    )
  }

  const stopped = STOPPED.includes(active.status)
  const steps = milestones(active, profile?.confirmed_at ?? null)
  const done = stopped ? doneCount(active.status_history.slice(-2)[0]?.to ?? 'selected') : doneCount(active.status)
  const forward = active.allowed_next.filter((s) => FORWARD.includes(s))
  const sideways = active.allowed_next.filter((s) => STOPPED.includes(s))
  const percent = Math.round((Math.min(done, steps.length) / steps.length) * 100)
  const earlier = outcomes.filter((o) => o.id !== active.id)

  return (
    <Layout>
      <FlowSteps current="journey" />

      <header className="journey-head">
        <div>
          <span className="eyebrow">Your journey</span>
          <h1 className="journey-head__title">
            {active.opportunity?.title ?? 'Your pathway'}
          </h1>
          <p className="muted" style={{ margin: 0 }}>
            {active.opportunity?.provider}
            {active.recommendation_id ? (
              <>
                {' · '}
                <a href={`/pathway/${active.recommendation_id}`} onClick={(e) => { e.preventDefault(); navigate(`/pathway/${active.recommendation_id}`) }}>
                  View pathway
                </a>
              </>
            ) : null}
          </p>
        </div>
        <div className="journey-meter" aria-label={`${percent}% of the way`}>
          <div className="journey-meter__bar">
            <span style={{ width: `${percent}%` }} />
          </div>
          <span className="small strong">
            {Math.min(done, steps.length)} of {steps.length} milestones
          </span>
        </div>
      </header>

      {justChose && active.status === 'selected' ? (
        <div className="celebrate enter">
          <Icon name="sparkle" size={20} />
          <span>
            <strong>Pathway chosen.</strong> Next: confirm your place. We’ll be with you at each step.
          </span>
        </div>
      ) : null}

      <div className="journey-grid">
        <ol className="timeline">
          {steps.map((step, i) => {
            const state = i < done ? 'done' : i === done && !stopped ? 'current' : 'next'
            return (
              <li key={step.key} className={`timeline__item is-${state} ${justDone === i ? 'just-done' : ''}`}>
                <span className="timeline__node">
                  <Icon name={state === 'done' ? 'check' : step.icon} size={state === 'done' ? 16 : 18} strokeWidth={state === 'done' ? 3 : 2} />
                </span>
                <div className="timeline__body">
                  <div className="timeline__title">
                    {state === 'done' ? step.doneTitle : step.title}
                    {state === 'current' ? <span className="timeline__now">Next</span> : null}
                  </div>
                  <div className="timeline__meta">
                    {state === 'done' ? (step.at ? formatDate(step.at) : 'Done') : state === 'current' ? 'Up next for you' : 'Later'}
                  </div>

                  {state === 'current' && forward.length > 0 ? (
                    <div className="timeline__actions">
                      {step.key === 'livelihood' ? (
                        <div className="income-field">
                          <label htmlFor="income" className="small">
                            Monthly income <span className="muted">(optional)</span>
                          </label>
                          <input id="income" type="number" min={0} inputMode="numeric" placeholder="₹" value={income} onChange={(e) => setIncome(e.target.value)} />
                        </div>
                      ) : null}
                      <div className="row">
                        {forward.map((status) => {
                          const action = OUTCOME_ACTION[status]
                          return (
                            <Button key={status} icon={action?.icon} onClick={() => advance.run(active, status)} loading={advance.pending}>
                              {action?.label ?? OUTCOME_WORD[status] ?? status}
                            </Button>
                          )
                        })}
                      </div>
                    </div>
                  ) : null}
                </div>
              </li>
            )
          })}
        </ol>

        <aside className="journey-side">
          {stopped ? (
            <div className="stopped-card">
              <Icon name="alert" size={20} />
              <div>
                <strong>{OUTCOME_WORD[active.status] ?? active.status}</strong>
                <p className="small muted" style={{ margin: '4px 0 12px' }}>
                  That’s fine — plans change. Your skills and profile are still here.
                </p>
                <Button size="sm" iconRight="arrowRight" onClick={() => navigate('/pathways')}>
                  Explore other pathways
                </Button>
              </div>
            </div>
          ) : null}

          <Feedback outcome={active} />

          {!stopped && sideways.length > 0 ? (
            <div className="changed">
              <button type="button" className="changed__toggle" aria-expanded={showStop} onClick={() => setShowStop((v) => !v)}>
                Something changed?
                <Icon name={showStop ? 'chevronDown' : 'chevronRight'} size={16} />
              </button>
              {showStop ? (
                <div className="changed__list enter">
                  {sideways.map((status) => {
                    const action = OUTCOME_ACTION[status]
                    return (
                      <Button key={status} variant={action?.tone === 'danger' ? 'danger' : 'secondary'} size="sm" icon={action?.icon} onClick={() => advance.run(active, status)} loading={advance.pending}>
                        {action?.label ?? status}
                      </Button>
                    )
                  })}
                </div>
              ) : null}
            </div>
          ) : null}

          {advance.error ? (
            <p className="small" role="alert" style={{ color: 'var(--red-700)' }}>
              We couldn’t save that update. Please try again.
            </p>
          ) : null}

          <details className="disclosure">
            <summary>
              <Icon name="clock" size={16} />
              <span className="grow">What has happened so far</span>
              <Icon name="chevronDown" size={18} className="disclosure__chev" />
            </summary>
            <ul className="history">
              {[...active.status_history].reverse().map((entry, i) => (
                <li key={i}>
                  <strong>{OUTCOME_WORD[entry.to] ?? entry.to}</strong>
                  <span className="tiny muted">
                    {formatDate(entry.at)} · recorded by {entry.actor}
                    {entry.note ? ` · ${entry.note}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          </details>

          {earlier.length > 0 ? (
            <div className="earlier">
              <div className="eyebrow">Earlier pathways</div>
              <ul>
                {earlier.map((o) => (
                  <li key={o.id}>
                    {o.opportunity?.title ?? 'Pathway'} <span className="muted">— {OUTCOME_WORD[o.status] ?? o.status}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </aside>
      </div>
    </Layout>
  )
}
