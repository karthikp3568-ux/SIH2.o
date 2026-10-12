/**
 * Pathways — the recommendations.
 *
 * The travel control re-runs the ranking server side. Cards that change place
 * say so ("Up from #3"), which is the clearest proof that distance and
 * mobility are ranking factors, not a filter bolted on at the end.
 */

import { useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import type { Recommendation, RecommendationRun } from '../api/types'
import { ComparePanel } from '../components/ComparePanel'
import { FlowSteps } from '../components/FlowSteps'
import { Icon } from '../components/Icon'
import { Layout } from '../components/Layout'
import { MapPanel } from '../components/MapPanel'
import type { MapPoint } from '../components/MapPanel'
import { PathwayCard } from '../components/PathwayCard'
import { WhyThisPanel } from '../components/WhyThisPanel'
import { Button, EmptyState, ErrorState, Loading } from '../components/ui'
import { useAction, useAsync } from '../hooks/useAsync'
import { loadMyRun } from '../lib/data'
import { MOBILITY_OPTIONS } from '../lib/labels'
import { opportunityKey } from '../lib/pathway'

function NoMatch({ run, onWiden, onTalk }: { run: RecommendationRun; onWiden: () => void; onTalk: () => void }) {
  const noMatch = run.no_match
  if (!noMatch) return null
  const closest = noMatch.closest_pathway
  return (
    <div className="no-match enter">
      <div className="no-match__head">
        <span className="icon-tile icon-tile--lg icon-tile--amber">
          <Icon name="search" size={26} />
        </span>
        <div>
          <h2 style={{ marginBottom: 6 }}>We couldn’t find a verified opportunity matching all your preferences.</h2>
          <p className="muted" style={{ margin: 0 }}>
            We won’t invent one to fill the space. Here’s where you stand, and what would open options up.
          </p>
        </div>
      </div>

      {closest ? (
        <div className="no-match__closest">
          <span className="eyebrow">Closest recognised pathway</span>
          <h3 style={{ margin: '4px 0' }}>{closest.title}</h3>
          {noMatch.missing_competencies.length > 0 ? (
            <ul className="tag-list" style={{ marginTop: 'var(--space-3)' }}>
              {noMatch.missing_competencies.map((c) => (
                <li key={c.code}>
                  <span className="need-chip">{c.name}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {noMatch.prerequisite_suggestions.length > 0 ? (
        <ul className="check-list">
          {noMatch.prerequisite_suggestions.map((s) => (
            <li key={s.competency_code}>
              <span className="check-list__mark check-list__mark--next">
                <Icon name="arrowRight" size={13} strokeWidth={2.6} />
              </span>
              <span>{s.suggestion}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="row">
        <Button icon="map" onClick={onWiden}>
          Broaden location
        </Button>
        <Button variant="secondary" icon="cap" onClick={onTalk}>
          Explore training pathways
        </Button>
      </div>
    </div>
  )
}

export function Pathways() {
  const navigate = useNavigate()
  const [run, setRun] = useState<RecommendationRun | null>(null)
  const [movedFrom, setMovedFrom] = useState<Map<string, number>>(new Map())
  const [why, setWhy] = useState<Recommendation | null>(null)
  const [hover, setHover] = useState<string | null>(null)
  const [comparing, setComparing] = useState(false)
  const closeWhy = useCallback(() => setWhy(null), [])

  const initial = useAsync(async () => {
    const [{ profile, run: latest }, opps] = await Promise.all([
      loadMyRun(),
      api.searchOpportunities({ limit: '100', include_unavailable: 'true' }).catch(() => null),
    ])
    setRun(latest)
    return { profile, opps }
  }, [])

  const rerank = useAction(async (payload: { mobility?: string; search_wider?: boolean }) => {
    const previous = new Map((run?.recommendations ?? []).map((r) => [opportunityKey(r), r.rank]))
    const fresh = await api.generate(payload)
    setMovedFrom(previous)
    setRun(fresh)
    return fresh
  })

  const points = useMemo<MapPoint[]>(() => {
    const opps = initial.data?.opps
    if (!opps || !run) return []
    const ranked = new Map(run.recommendations.map((r) => [opportunityKey(r), r]))
    return opps.items
      .filter((o) => o.latitude !== null && o.longitude !== null)
      .map((o) => {
        const rec = ranked.get(opportunityKey(o))
        return {
          id: rec?.id ?? o.id,
          title: o.title,
          provider: o.provider,
          type: o.opportunity_type,
          latitude: o.latitude!,
          longitude: o.longitude!,
          distanceKm: rec?.distance_km ?? opps.distances_km[o.id] ?? null,
          rank: rec?.rank,
          available: o.status === 'active',
          verificationStatus: o.verification_status,
          lastVerifiedAt: o.last_verified_at,
          validUntil: o.valid_until,
        }
      })
  }, [initial.data, run])

  if (initial.loading) {
    return (
      <Layout>
        <Loading label="Finding pathways near you…" />
      </Layout>
    )
  }
  if (initial.error || !run || !initial.data) {
    return (
      <Layout>
        <EmptyState
          icon="route"
          title="No pathways yet"
          description="Tell us about your work and we’ll find training and work that fits — near you."
          action={
            <Button icon="mic" onClick={() => navigate('/start?mode=voice&fresh=1')}>
              Start talking
            </Button>
          }
        />
      </Layout>
    )
  }

  const { profile } = initial.data
  const recs = run.recommendations
  const location = profile.location
  const mobility = run.mobility_used

  return (
    <Layout>
      <FlowSteps current="pathways" />

      <header className="page-head page-head--split">
        <div>
          <span className="eyebrow">Your pathways</span>
          <h1 className="display-2" style={{ margin: '6px 0 8px' }}>
            {run.is_no_match
              ? 'Nothing fits every preference yet'
              : `${recs.length} pathway${recs.length === 1 ? '' : 's'} fit your profile`}
          </h1>
          <p className="lead" style={{ margin: 0, maxWidth: '54ch' }}>
            Suggestions, not decisions. Each one says why it fits and what you’d still need.
          </p>
        </div>

        <div className="travel-control">
          <span className="eyebrow">How far can you travel?</span>
          <div className="segmented" role="group" aria-label="How far can you travel">
            {MOBILITY_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={mobility === option.value}
                disabled={rerank.pending}
                onClick={() => option.value !== mobility && rerank.run({ mobility: option.value })}
              >
                <Icon name={option.icon} size={16} /> {option.short}
              </button>
            ))}
          </div>
          <span className="tiny muted">
            {rerank.pending ? 'Updating…' : `Showing options within ${run.radius_km_used ?? '—'} km of you`}
          </span>
        </div>
      </header>

      {rerank.error ? <ErrorState title="We couldn’t re-rank right now" message="Your earlier results are still shown." /> : null}

      {run.is_no_match ? (
        <NoMatch
          run={run}
          onWiden={() => rerank.run({ search_wider: true, mobility: 'high' })}
          onTalk={() => navigate('/skills')}
        />
      ) : (
        <div className={`paths ${rerank.pending ? 'is-busy' : ''}`}>
          <div className="paths__list" key={run.run_id}>
            {recs.map((rec, i) => (
              <PathwayCard
                key={rec.id}
                rec={rec}
                index={i}
                mobility={mobility}
                movedFrom={movedFrom.get(opportunityKey(rec)) ?? null}
                highlighted={hover === rec.id}
                onHover={(on) => setHover(on ? rec.id : null)}
                onWhy={() => setWhy(rec)}
                onOpen={() => navigate(`/pathway/${rec.id}`)}
              />
            ))}
          </div>

          <aside className="paths__side">
            {location?.latitude != null && location?.longitude != null ? (
              <MapPanel
                origin={{ latitude: location.latitude, longitude: location.longitude, label: location.label ?? location.village ?? 'Your location' }}
                points={points}
                radiusKm={run.radius_km_used}
                highlight={hover}
                onHighlight={setHover}
              />
            ) : (
              <div className="map-panel map-panel--empty">
                <Icon name="pin" size={28} />
                <strong>We couldn’t detect your location.</strong>
                <p className="small muted">Add it to see distances on a map.</p>
                <Button variant="secondary" size="sm" onClick={() => navigate('/profile')}>
                  Enter manually
                </Button>
              </div>
            )}

            {recs.length > 1 ? (
              <button type="button" className="compare-toggle" aria-expanded={comparing} onClick={() => setComparing((v) => !v)}>
                <span className="icon-tile icon-tile--sm icon-tile--blue">
                  <Icon name="columns" size={17} />
                </span>
                <span className="grow">
                  <strong>Compare side by side</strong>
                  <span className="small muted">Skill fit, distance, eligibility, gap</span>
                </span>
                <Icon name={comparing ? 'chevronDown' : 'chevronRight'} size={18} />
              </button>
            ) : null}
          </aside>
        </div>
      )}

      {comparing && recs.length > 1 ? (
        <section className="compare-section" aria-label="Compare pathways">
          <h2>Side by side</h2>
          <ComparePanel recs={recs} onOpen={(r) => navigate(`/pathway/${r.id}`)} />
        </section>
      ) : null}

      <WhyThisPanel rec={why} onClose={closeWhy} />
    </Layout>
  )
}
