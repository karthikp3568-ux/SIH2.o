/**
 * One pathway, end to end: from what the person has today, through training,
 * to an opportunity and a livelihood. Every section is drawn from the
 * explanation the ranking produced — nothing here is model-written text.
 */

import { useCallback, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { api } from '../api/client'
import { FlowSteps } from '../components/FlowSteps'
import { Icon, OPPORTUNITY_TYPE } from '../components/Icon'
import type { IconName } from '../components/Icon'
import { Layout } from '../components/Layout'
import { MapPanel } from '../components/MapPanel'
import { WhyThisPanel } from '../components/WhyThisPanel'
import { Button, Chip, ErrorState, Loading, TrustBadge, formatDate, formatInr } from '../components/ui'
import { useAction, useAsync } from '../hooks/useAsync'
import { loadMyRun } from '../lib/data'
import { matchLabel } from '../lib/labels'
import { availabilityWord, nextSteps, opportunityKey } from '../lib/pathway'

export function PathwayDetail() {
  const { recommendationId } = useParams<{ recommendationId: string }>()
  const navigate = useNavigate()
  const [whyOpen, setWhyOpen] = useState(false)
  const closeWhy = useCallback(() => setWhyOpen(false), [])

  const data = useAsync(async () => {
    if (!recommendationId) throw new Error('Missing pathway')
    const [explanation, mine, opps] = await Promise.all([
      api.explanation(recommendationId),
      loadMyRun(),
      api.searchOpportunities({ limit: '100', include_unavailable: 'true' }).catch(() => null),
    ])
    return { explanation, ...mine, opps }
  }, [recommendationId])

  const choose = useAction(async (pathwayId: string) => {
    await api.selectPathway(pathwayId)
    navigate('/journey', { state: { justChose: true } })
    return true
  })

  if (data.loading) {
    return (
      <Layout>
        <Loading label="Opening this pathway…" />
      </Layout>
    )
  }
  if (data.error || !data.data) {
    return (
      <Layout>
        <ErrorState
          title="We couldn’t open this pathway"
          message="It may have been replaced by a newer set of suggestions."
          onRetry={() => navigate('/pathways')}
          retryLabel="See current pathways"
        />
      </Layout>
    )
  }

  const { explanation: ex, run, profile, opps } = data.data
  const rec = run.recommendations.find((r) => r.id === recommendationId) ?? null
  const gap = ex.skill_gap_detail
  const type = OPPORTUNITY_TYPE[rec?.opportunity_type ?? 'training'] ?? OPPORTUNITY_TYPE.training
  const match = matchLabel(ex.match_score)
  const opp = rec ? opps?.items.find((o) => opportunityKey(o) === opportunityKey(rec)) : undefined
  const others = run.recommendations.filter((r) => r.id !== recommendationId)
  const toLearn = (gap?.missing.length ?? 0) + (gap?.partial.length ?? 0)
  const income = formatInr(rec?.stipend_or_income_inr)

  const journey: { icon: IconName; title: string; body: string; state: 'here' | 'next' }[] = [
    { icon: 'user', title: 'You', body: rec?.skills_you_have.slice(0, 2).map((s) => s.name).join(', ') || 'Your experience', state: 'here' },
    { icon: type.icon, title: type.label, body: rec?.provider ?? '', state: 'next' },
    { icon: 'graph', title: 'Skill development', body: toLearn ? `${toLearn} competenc${toLearn === 1 ? 'y' : 'ies'} to build` : 'Strengthen what you have', state: 'next' },
    { icon: 'briefcase', title: 'Opportunity', body: rec?.opportunity_type === 'job' ? 'This job' : 'Work or your own service', state: 'next' },
    { icon: 'sprout', title: 'Livelihood', body: income ? `${income} a month stated` : 'Steady income', state: 'next' },
  ]

  const shareWhatsApp = () => {
    const title = gap?.qualification_title ?? ex.title
    const provider = rec?.provider ?? 'Verified Provider'
    const distance = rec?.distance_km != null ? `${Math.round(rec.distance_km)} km` : 'Local'
    const stipend = income ? `\n💰 Stipend/Income: ${income}` : ''
    const nsqf = gap?.nsqf_level ? `\n📜 NSQF Level: ${gap.nsqf_level}` : ''
    const msg = `*Livelihood Navigator Pathway*\n\n🎯 *Pathway:* ${title}\n🏢 *Provider:* ${provider}\n📍 *Distance:* ${distance}${nsqf}${stipend}\n\nExplore this pathway: ${window.location.href}`
    window.open(`https://wa.me/?text=${encodeURIComponent(msg)}`, '_blank', 'noopener,noreferrer')
  }

  return (
    <Layout>
      <FlowSteps current="pathways" />

      <button type="button" className="back-link" onClick={() => navigate('/pathways')}>
        <Icon name="arrowLeft" size={16} /> All pathways
      </button>

      <header className="detail-hero enter">
        <div className="detail-hero__main">
          <span className="eyebrow">
            <Icon name={type.icon} size={14} /> {type.label} · Your pathway
          </span>
          <h1 className="display-2">{gap?.qualification_title ?? ex.title}</h1>
          <p className="detail-hero__sub">
            {ex.title}
            {rec ? ` — ${rec.provider}` : ''}
          </p>
          <div className="detail-hero__facts">
            <span className={`match-pill match-pill--${match.tone}`}>
              <Icon name="sparkle" size={14} /> {match.label}
            </span>
            {rec?.distance_km != null ? (
              <Chip icon="pin" size="lg">
                {rec.distance_km < 1 ? 'In your village' : `${Math.round(rec.distance_km)} km from you`}
              </Chip>
            ) : null}
            {gap?.nsqf_level ? (
              <Chip icon="cap" size="lg">
                NSQF level {gap.nsqf_level}
                {gap.qualification_code ? ` · ${gap.qualification_code}` : ''}
              </Chip>
            ) : null}
            {rec ? <TrustBadge verificationStatus={rec.verification_status} lastVerifiedAt={rec.last_verified_at} validUntil={rec.valid_until} /> : null}
          </div>
        </div>
        <div className="detail-hero__actions">
          {rec?.is_selected ? (
            <Button size="lg" variant="success" icon="flag" onClick={() => navigate('/journey')}>
              Track this pathway
            </Button>
          ) : (
            <Button size="lg" icon="check" onClick={() => choose.run(ex.pathway_id)} loading={choose.pending}>
              Choose this pathway
            </Button>
          )}
          <Button variant="secondary" icon="info" onClick={() => setWhyOpen(true)}>
            Why this?
          </Button>
          <Button variant="secondary" icon="messageCircle" onClick={shareWhatsApp} title="Send summary to WhatsApp">
            WhatsApp
          </Button>
        </div>
      </header>

      <ol className="route" aria-label="Your route">
        {journey.map((step, i) => (
          <li key={step.title} className={`route__step is-${step.state} enter`} style={{ animationDelay: `${150 + i * 110}ms` }}>
            <span className="route__icon">
              <Icon name={step.icon} size={22} />
            </span>
            <span className="route__title">{step.title}</span>
            <span className="route__body">{step.body}</span>
          </li>
        ))}
      </ol>

      <div className="detail-cols">
        <section className="detail-block detail-block--have">
          <h2>
            <Icon name="checkCircle" size={20} /> What you already have
          </h2>
          <ul className="check-list">
            {(gap?.covered ?? []).map((c) => (
              <li key={c.code}>
                <span className="check-list__mark check-list__mark--have">
                  <Icon name="check" size={13} strokeWidth={3} />
                </span>
                <div>
                  <div className="strong">{c.name}</div>
                  <div className="check-list__detail">{c.explanation}</div>
                </div>
              </li>
            ))}
            {(rec?.skills_you_have ?? []).length > 0 ? (
              <li>
                <span className="check-list__mark check-list__mark--have">
                  <Icon name="wrench" size={12} />
                </span>
                <div>
                  <div className="strong">Your skills that count</div>
                  <ul className="tag-list" style={{ marginTop: 6 }}>
                    {rec!.skills_you_have.map((s) => (
                      <li key={s.code}>
                        <Chip tone="good">{s.name}</Chip>
                      </li>
                    ))}
                  </ul>
                </div>
              </li>
            ) : null}
          </ul>
        </section>

        <section className="detail-block detail-block--need">
          <h2>
            <Icon name="target" size={20} /> What you’ll learn
          </h2>
          {toLearn === 0 ? (
            <p className="muted">Nothing missing — you already cover this standard.</p>
          ) : (
            <ul className="check-list">
              {[...(gap?.missing ?? []), ...(gap?.partial ?? [])].map((c) => (
                <li key={c.code}>
                  <span className={`check-list__mark ${c.band === 'partial' ? 'check-list__mark--warn' : 'check-list__mark--need'}`}>
                    {c.band === 'partial' ? <Icon name="activity" size={12} strokeWidth={2.6} /> : null}
                  </span>
                  <div>
                    <div className="strong">
                      {c.name} {c.band === 'partial' ? <Chip tone="warn">Partly there</Chip> : null}
                    </div>
                    <div className="check-list__detail">
                      {c.is_core ? 'Core' : 'Elective'}
                      {c.nos_code ? ` · ${c.nos_code}` : ''}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="detail-where">
        <div className="detail-block">
          <h2>
            <Icon name="pin" size={20} /> Where
          </h2>
          <dl className="where-facts">
            <div>
              <dt>Provider</dt>
              <dd>{rec?.provider ?? '—'}</dd>
            </div>
            <div>
              <dt>Location</dt>
              <dd>
                {rec?.location_label ?? rec?.district ?? '—'}
                {rec?.distance_km != null ? <span className="muted"> · {Math.round(rec.distance_km)} km from you</span> : null}
              </dd>
            </div>
            {rec ? (
              <div>
                <dt>Availability</dt>
                <dd>
                  {availabilityWord(rec).label}
                  {rec.seats_available ? ` · ${rec.seats_available} seats left` : ''}
                </dd>
              </div>
            ) : null}
            {income ? (
              <div>
                <dt>{rec?.opportunity_type === 'training' ? 'Stipend' : 'Stated income'}</dt>
                <dd>{income} / month</dd>
              </div>
            ) : null}
            {rec?.valid_until ? (
              <div>
                <dt>Open until</dt>
                <dd>{formatDate(rec.valid_until)}</dd>
              </div>
            ) : null}
            <div>
              <dt>Source</dt>
              <dd>
                {String(ex.evidence?.source ?? rec?.source ?? 'Not stated')}
                {ex.evidence?.source_url ? (
                  <>
                    {' · '}
                    <a href={String(ex.evidence.source_url)} target="_blank" rel="noreferrer noopener">
                      Open source
                    </a>
                  </>
                ) : null}
              </dd>
            </div>
          </dl>
        </div>
        {opp && opp.latitude != null && profile.location?.latitude != null && rec ? (
          <MapPanel
            origin={{ latitude: profile.location.latitude, longitude: profile.location.longitude!, label: profile.location.label ?? 'You' }}
            points={[
              {
                id: rec.id,
                title: opp.title,
                provider: opp.provider,
                type: opp.opportunity_type,
                latitude: opp.latitude,
                longitude: opp.longitude!,
                distanceKm: rec.distance_km,
                rank: rec.rank,
                available: opp.status === 'active',
                verificationStatus: opp.verification_status,
                lastVerifiedAt: opp.last_verified_at,
                validUntil: opp.valid_until,
              },
            ]}
            radiusKm={run.radius_km_used}
          />
        ) : null}
      </section>

      <section className="next-steps">
        <h2>What happens next</h2>
        {ex.next_step ? (
          <p className="next-steps__lead">
            <Icon name="flag" size={18} /> {ex.next_step.label}
          </p>
        ) : null}
        <ol className="steps-row">
          {nextSteps(rec?.opportunity_type ?? 'training').map((step, i) => (
            <li key={step.title}>
              <span className="steps-row__num">{String(i + 1).padStart(2, '0')}</span>
              <span className="steps-row__icon">
                <Icon name={step.icon} size={20} />
              </span>
              <strong>{step.title}</strong>
              <span>{step.body}</span>
            </li>
          ))}
        </ol>
      </section>

      {others.length > 0 ? (
        <section className="others">
          <h2>Other pathways for you</h2>
          <div className="others__list">
            {others.map((r) => {
              const m = matchLabel(r.match_score)
              const t = OPPORTUNITY_TYPE[r.opportunity_type] ?? OPPORTUNITY_TYPE.training
              return (
                <button key={r.id} type="button" className="other-row" onClick={() => navigate(`/pathway/${r.id}`)}>
                  <span className="icon-tile icon-tile--sm icon-tile--blue">
                    <Icon name={t.icon} size={17} />
                  </span>
                  <span className="grow">
                    <strong>{r.qualification?.title ?? r.title}</strong>
                    <span className="small muted">
                      {r.provider}
                      {r.distance_km != null ? ` · ${Math.round(r.distance_km)} km` : ''}
                    </span>
                  </span>
                  <span className={`match-pill match-pill--${m.tone}`}>{m.label}</span>
                  <Icon name="chevronRight" size={18} />
                </button>
              )
            })}
          </div>
        </section>
      ) : null}

      {choose.error ? <ErrorState title="We couldn’t record your choice" message="Please try again in a moment." /> : null}

      <div className="confirm-dock">
        <div className="confirm-dock__inner">
          <div className="grow">
            <strong>{gap?.qualification_title ?? ex.title}</strong>
            <span className="small muted"> · You can change your mind later.</span>
          </div>
          <Button variant="secondary" icon="columns" onClick={() => navigate('/pathways')}>
            Compare
          </Button>
          {rec?.is_selected ? (
            <Button size="lg" variant="success" icon="flag" onClick={() => navigate('/journey')}>
              Track this pathway
            </Button>
          ) : (
            <Button size="lg" icon="check" onClick={() => choose.run(ex.pathway_id)} loading={choose.pending}>
              Choose this pathway
            </Button>
          )}
        </div>
      </div>

      <WhyThisPanel rec={whyOpen ? rec : null} onClose={closeWhy} />
    </Layout>
  )
}
