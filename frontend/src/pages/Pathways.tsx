/**
 * Screen 3 — "Your possible pathways".
 *
 * Includes the mobility control, because watching the ranking change when the
 * travel limit changes is the clearest demonstration that this is not a
 * similarity search. Also includes the first-class no-match view and the
 * "why some options are not shown" disclosure.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import { Layout } from '../components/Layout'
import { PathwayCard } from '../components/PathwayCard'
import { SkillGraphView } from '../components/SkillGraphView'
import { Button, Card, Chip, EmptyState, ErrorState, Loading, Notice } from '../components/ui'
import { useAction, useAsync } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'
import type { Recommendation, RecommendationRun } from '../api/types'

const MOBILITY_CHOICES = [
  { value: 'low', icon: '🏠', key: 'mobility.low' },
  { value: 'medium', icon: '🚌', key: 'mobility.medium' },
  { value: 'high', icon: '🚆', key: 'mobility.high' },
]

function NoMatchView({ run, onWiden }: { run: RecommendationRun; onWiden: () => void }) {
  const noMatch = run.no_match
  if (!noMatch) return null
  return (
    <div className="stack">
      <Notice tone="warn" title={noMatch.message}>
        <p className="small" style={{ margin: 0 }}>
          We will not invent an opportunity to fill this space. Here is where you actually stand and
          what would open options up.
        </p>
      </Notice>

      {noMatch.closest_pathway ? (
        <Card>
          <h3>Closest recognised pathway for you</h3>
          <div className="row row--between" style={{ marginBottom: 'var(--space-3)' }}>
            <div>
              <strong>{noMatch.closest_pathway.title}</strong>
              <p className="small muted" style={{ margin: 0 }}>
                {noMatch.closest_pathway.qualification_code} ·{' '}
                {noMatch.closest_pathway.nsqf_level
                  ? `NSQF level ${noMatch.closest_pathway.nsqf_level}`
                  : 'level not stated'}
              </p>
            </div>
            <Chip tone="info" icon="◎">
              {Math.round((noMatch.closest_pathway.coverage_ratio ?? 0) * 100)}% covered
            </Chip>
          </div>
          {noMatch.missing_competencies.length > 0 ? (
            <>
              <p className="small strong">What you would need</p>
              <ul className="reason-list">
                {noMatch.missing_competencies.map((competency) => (
                  <li key={competency.code}>
                    <span className="reason-list__icon" aria-hidden="true">
                      ○
                    </span>
                    <span className="small">{competency.name}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          <p className="tiny muted" style={{ marginTop: 'var(--space-3)', marginBottom: 0 }}>
            Source: {noMatch.closest_pathway.source}
          </p>
        </Card>
      ) : null}

      {noMatch.prerequisite_suggestions.length > 0 ? (
        <Card>
          <h3>Where to start</h3>
          <ul className="reason-list">
            {noMatch.prerequisite_suggestions.map((suggestion) => (
              <li key={suggestion.competency_code}>
                <span className="reason-list__icon" aria-hidden="true">
                  →
                </span>
                <span className="small">{suggestion.suggestion}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Card>
        <h3>What to check next</h3>
        <ul className="reason-list">
          {noMatch.what_to_verify.map((item, index) => (
            <li key={index}>
              <span className="reason-list__icon" aria-hidden="true">
                •
              </span>
              <span className="small">{item}</span>
            </li>
          ))}
        </ul>
        <div className="row" style={{ marginTop: 'var(--space-4)' }}>
          {noMatch.retry_options.some((option) => option.action === 'widen_radius') ? (
            <Button icon="🔍" onClick={onWiden}>
              Search a wider area
            </Button>
          ) : null}
        </div>
      </Card>
    </div>
  )
}

function ExclusionsPanel({ run }: { run: RecommendationRun }) {
  const grouped = new Map<string, { reason: string; items: typeof run.exclusions }>()
  for (const exclusion of run.exclusions ?? []) {
    const entry = grouped.get(exclusion.reason_code) ?? { reason: exclusion.reason, items: [] }
    entry.items.push(exclusion)
    grouped.set(exclusion.reason_code, entry)
  }
  if (grouped.size === 0) return null

  return (
    <details className="card">
      <summary style={{ cursor: 'pointer', fontWeight: 650 }}>
        Why some options are not shown ({run.exclusions.length})
      </summary>
      <p className="small muted" style={{ marginTop: 'var(--space-3)' }}>
        We looked at {run.candidates_considered} listing
        {run.candidates_considered === 1 ? '' : 's'} and {run.candidates_after_filters} passed the
        eligibility and availability checks. Everything removed is listed with its reason.
      </p>
      {[...grouped.entries()].map(([code, group]) => (
        <div key={code} style={{ marginTop: 'var(--space-3)' }}>
          <p className="small strong" style={{ marginBottom: 4 }}>
            {group.reason} ({group.items.length})
          </p>
          <ul className="reason-list">
            {group.items.map((item, index) => (
              <li key={index}>
                <span className="reason-list__icon" aria-hidden="true">
                  ✕
                </span>
                <span className="small">
                  {item.title}
                  {item.detail ? <span className="muted"> — {item.detail}</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </details>
  )
}

export function Pathways() {
  const { t } = useApp()
  const navigate = useNavigate()
  const [mobility, setMobility] = useState<string | null>(null)
  const [run, setRun] = useState<RecommendationRun | null>(null)
  const [showGraph, setShowGraph] = useState(false)

  const initial = useAsync(async () => {
    const profile = await api.profile()
    let current: RecommendationRun
    try {
      current = await api.latestRun(profile.id)
    } catch {
      current = await api.generate({})
    }
    setRun(current)
    setMobility(current.mobility_used)
    return { profile, run: current }
  }, [])

  const graph = useAsync(
    async () => (initial.data ? api.skillGraph(initial.data.profile.id) : null),
    [initial.data?.profile.id],
  )

  const regenerate = useAction(async (nextMobility?: string, searchWider = false) => {
    const fresh = await api.generate({
      mobility: nextMobility ?? mobility ?? undefined,
      search_wider: searchWider,
    })
    setRun(fresh)
    if (nextMobility) setMobility(nextMobility)
    return fresh
  })

  const openDetail = (recommendation: Recommendation) => {
    navigate(`/pathway/${recommendation.id}`)
  }

  if (initial.loading) {
    return (
      <Layout>
        <Loading label={t('common.loading')} />
      </Layout>
    )
  }
  if (initial.error || !run) {
    return (
      <Layout>
        <ErrorState message={initial.error ?? 'Could not load your pathways.'} onRetry={initial.reload} />
      </Layout>
    )
  }

  return (
    <Layout>
      <div className="stack">
        <div>
          <h1>{t('pathways.title')}</h1>
          <p className="muted">{t('pathways.subtitle')}</p>
        </div>

        <Card>
          <h3 style={{ fontSize: '1rem' }}>{t('pathways.changeTravel')}</h3>
          <div className="choice-grid grid--3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))' }}>
            {MOBILITY_CHOICES.map((choice) => (
              <button
                key={choice.value}
                type="button"
                className="choice"
                aria-pressed={mobility === choice.value}
                onClick={() => regenerate.run(choice.value)}
                disabled={regenerate.pending}
              >
                <span className="choice__icon" aria-hidden="true">
                  {choice.icon}
                </span>
                <span>{t(choice.key)}</span>
              </button>
            ))}
          </div>
          <p className="tiny muted" style={{ marginTop: 'var(--space-3)', marginBottom: 0 }}>
            Searching within {run.radius_km_used ?? '—'} km. Changing this changes what you see, and
            in what order — distance is one of nine factors, not a filter bolted on at the end.
          </p>
        </Card>

        {regenerate.pending ? <Loading label="Finding pathways…" /> : null}
        {regenerate.error ? <ErrorState message={regenerate.error} /> : null}

        {run.is_no_match ? (
          <NoMatchView run={run} onWiden={() => regenerate.run(undefined, true)} />
        ) : run.recommendations.length === 0 ? (
          <EmptyState
            icon="🔍"
            title="No pathways yet"
            description="Tell us about your work and we will find pathways for you."
            action={<Button onClick={() => navigate('/start')}>Start</Button>}
          />
        ) : (
          <div className="stack">
            {run.recommendations.map((recommendation) => (
              <PathwayCard
                key={recommendation.id}
                recommendation={recommendation}
                onOpen={openDetail}
              />
            ))}
          </div>
        )}

        <ExclusionsPanel run={run} />

        {graph.data ? (
          <Card>
            <div className="row row--between">
              <h3 style={{ margin: 0 }}>Your skills</h3>
              <Button variant="ghost" onClick={() => setShowGraph((value) => !value)}>
                {showGraph ? 'Hide' : 'Show'}
              </Button>
            </div>
            {showGraph ? (
              <div style={{ marginTop: 'var(--space-4)' }}>
                <SkillGraphView graph={graph.data} name={initial.data?.profile.display_name ?? 'You'} />
              </div>
            ) : null}
          </Card>
        ) : null}

        <details className="card card--quiet">
          <summary style={{ cursor: 'pointer', fontWeight: 650 }}>How pathways are ordered</summary>
          <p className="small muted" style={{ marginTop: 'var(--space-3)' }}>
            Each pathway is scored on nine factors and ordered by the weighted average. These
            weights are our product judgement, chosen so no single factor dominates — they are not
            empirically validated figures.
          </p>
          <ul className="reason-list">
            {run.ranking_weights.map((weight) => (
              <li key={weight.code}>
                <span className="reason-list__icon" aria-hidden="true">
                  •
                </span>
                <span className="small" style={{ flex: 1 }}>
                  {weight.label}
                </span>
                <span className="small muted">{Math.round(weight.share * 100)}%</span>
              </li>
            ))}
          </ul>
        </details>
      </div>
    </Layout>
  )
}
