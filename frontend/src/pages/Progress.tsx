/**
 * Screen 5 — outcome tracking and feedback.
 *
 * Objective lifecycle events and subjective feedback are collected separately,
 * mirroring the backend: how it went and how it felt are different facts.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import { Layout } from '../components/Layout'
import { Button, Card, Chip, EmptyState, ErrorState, Loading, Notice, formatDate } from '../components/ui'
import { useAction, useAsync } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'
import type { Outcome } from '../api/types'

const JOURNEY = [
  { key: 'selected', label: 'Chosen', icon: '◎' },
  { key: 'enrolled', label: 'Enrolled', icon: '📝' },
  { key: 'attending', label: 'Attending', icon: '📘' },
  { key: 'completed', label: 'Completed', icon: '🎓' },
  { key: 'working', label: 'Working', icon: '💼' },
]

const STATUS_LABEL: Record<string, string> = {
  selected: 'Chosen',
  enrolled: 'Enrolled',
  attending: 'Attending',
  completed: 'Completed',
  employed: 'Employed',
  self_employed: 'Self-employed',
  dropped_out: 'Stopped',
  rejected: 'Not taken up',
  changed_pathway: 'Changed pathway',
  opportunity_inactive: 'Opportunity closed',
}

function journeyIndex(status: string): number {
  if (status === 'employed' || status === 'self_employed') return 4
  const index = JOURNEY.findIndex((step) => step.key === status)
  return index >= 0 ? index : 0
}

function JourneySteps({ status }: { status: string }) {
  const current = journeyIndex(status)
  return (
    <ol className="steps">
      {JOURNEY.map((step, index) => (
        <li
          key={step.key}
          className={`step ${index < current ? 'step--done' : index === current ? 'step--current' : ''}`}
        >
          <span aria-hidden="true">{index < current ? '✓' : step.icon}</span>
          {step.label}
        </li>
      ))}
    </ol>
  )
}

function FeedbackForm({ outcome, onDone }: { outcome: Outcome; onDone: () => void }) {
  const { t } = useApp()
  const [useful, setUseful] = useState<boolean | null>(null)
  const [reason, setReason] = useState('')
  const [comment, setComment] = useState('')
  const [sent, setSent] = useState(false)
  const reasons = useAsync(() => api.feedbackReasons(), [])

  const submit = useAction(async () => {
    await api.feedback({
      outcome_id: outcome.id,
      recommendation_id: outcome.recommendation_id,
      opportunity_id: outcome.opportunity_id,
      was_useful: useful,
      rejection_reason: useful === false && reason ? reason : undefined,
      comment: comment || undefined,
    })
    setSent(true)
    onDone()
    return true
  })

  if (sent) {
    return (
      <Notice tone="success">
        <p style={{ margin: 0 }}>{t('progress.thanks')}</p>
      </Notice>
    )
  }

  return (
    <Card>
      <h3>{t('progress.feedback')}</h3>
      <p className="small muted">{t('progress.wasUseful')}</p>
      <div className="row" style={{ marginBottom: 'var(--space-4)' }}>
        <button
          type="button"
          className="choice"
          aria-pressed={useful === true}
          onClick={() => setUseful(true)}
          style={{ flex: 1 }}
        >
          <span className="choice__icon" aria-hidden="true">
            👍
          </span>
          {t('progress.yes')}
        </button>
        <button
          type="button"
          className="choice"
          aria-pressed={useful === false}
          onClick={() => setUseful(false)}
          style={{ flex: 1 }}
        >
          <span className="choice__icon" aria-hidden="true">
            👎
          </span>
          {t('progress.no')}
        </button>
      </div>

      {useful === false ? (
        <div className="field">
          <label htmlFor="reason">{t('progress.whyNot')}</label>
          <select id="reason" value={reason} onChange={(event) => setReason(event.target.value)}>
            <option value="">Choose a reason…</option>
            {(reasons.data ?? []).map((option) => (
              <option key={option.code} value={option.code}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      <div className="field">
        <label htmlFor="comment">Anything else you want to tell us?</label>
        <textarea
          id="comment"
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          rows={3}
        />
      </div>

      {submit.error ? <ErrorState message={submit.error} /> : null}

      <Button
        onClick={() => submit.run()}
        loading={submit.pending}
        disabled={useful === null}
        icon="➤"
      >
        {t('progress.submit')}
      </Button>
    </Card>
  )
}

export function Progress() {
  const { t } = useApp()
  const navigate = useNavigate()
  const outcomes = useAsync(() => api.outcomes(), [])
  const [note, setNote] = useState('')

  const advance = useAction(async (outcomeId: string, status: string) => {
    await api.updateOutcome(outcomeId, { status, note: note || undefined })
    setNote('')
    outcomes.reload()
    return true
  })

  if (outcomes.loading) {
    return (
      <Layout>
        <Loading label={t('common.loading')} />
      </Layout>
    )
  }
  if (outcomes.error) {
    return (
      <Layout>
        <ErrorState message={outcomes.error} onRetry={outcomes.reload} />
      </Layout>
    )
  }

  const rows = outcomes.data ?? []
  const active = rows.find((row) => row.is_active) ?? rows[0]

  if (!active) {
    return (
      <Layout>
        <EmptyState
          icon="🧭"
          title={t('progress.none')}
          description="Choose a pathway and we will track it here from training to livelihood."
          action={<Button onClick={() => navigate('/pathways')}>{t('nav.pathways')}</Button>}
        />
      </Layout>
    )
  }

  return (
    <Layout>
      <div className="stack">
        <h1>{t('progress.title')}</h1>

        <Card>
          <div className="row row--between" style={{ marginBottom: 'var(--space-4)' }}>
            <div>
              <h2 style={{ marginBottom: 2 }}>{active.opportunity?.title ?? 'Your pathway'}</h2>
              <p className="small muted" style={{ margin: 0 }}>
                {active.opportunity?.provider}
              </p>
            </div>
            <Chip tone={active.is_active ? 'good' : 'neutral'} icon="●">
              {STATUS_LABEL[active.status] ?? active.status}
            </Chip>
          </div>

          <JourneySteps status={active.status} />

          {active.allowed_next.length > 0 ? (
            <div style={{ marginTop: 'var(--space-5)' }}>
              <h3 style={{ fontSize: '1rem' }}>{t('progress.update')}</h3>
              <div className="field">
                <label htmlFor="note">Add a note (optional)</label>
                <input
                  id="note"
                  type="text"
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="e.g. Batch started on Monday"
                />
              </div>
              <div className="row" style={{ marginTop: 'var(--space-3)' }}>
                {active.allowed_next.map((status) => (
                  <Button
                    key={status}
                    variant={
                      status === 'dropped_out' || status === 'rejected' ? 'danger' : 'secondary'
                    }
                    onClick={() => advance.run(active.id, status)}
                    loading={advance.pending}
                  >
                    {STATUS_LABEL[status] ?? status}
                  </Button>
                ))}
              </div>
              {advance.error ? (
                <p className="small" style={{ color: 'var(--red-700)', marginTop: 'var(--space-3)' }}>
                  {advance.error}
                </p>
              ) : null}
            </div>
          ) : null}
        </Card>

        <Card>
          <h3>What has happened so far</h3>
          <ul className="reason-list">
            {active.status_history.map((entry, index) => (
              <li key={index}>
                <span className="reason-list__icon" aria-hidden="true">
                  •
                </span>
                <div>
                  <div className="small">
                    <span className="strong">{STATUS_LABEL[entry.to] ?? entry.to}</span>
                    {entry.from ? <span className="muted"> (from {STATUS_LABEL[entry.from] ?? entry.from})</span> : null}
                  </div>
                  <div className="tiny muted">
                    {formatDate(entry.at)} · recorded by {entry.actor}
                    {entry.note ? ` · ${entry.note}` : ''}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <FeedbackForm outcome={active} onDone={outcomes.reload} />

        {rows.length > 1 ? (
          <Card>
            <h3>Earlier pathways</h3>
            <ul className="reason-list">
              {rows
                .filter((row) => row.id !== active.id)
                .map((row) => (
                  <li key={row.id}>
                    <span className="reason-list__icon" aria-hidden="true">
                      ◦
                    </span>
                    <div className="small">
                      {row.opportunity?.title ?? row.opportunity_id} —{' '}
                      <span className="muted">{STATUS_LABEL[row.status] ?? row.status}</span>
                    </div>
                  </li>
                ))}
            </ul>
          </Card>
        ) : null}
      </div>
    </Layout>
  )
}
