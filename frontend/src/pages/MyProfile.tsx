/**
 * My Profile — the confirmed profile, as the person sees it.
 *
 * Travel distance can be changed here directly because it is the constraint
 * people most often revise, and it immediately re-ranks their pathways.
 * Anything larger goes back through conversation and confirmation.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import { Icon } from '../components/Icon'
import type { IconName } from '../components/Icon'
import { Layout } from '../components/Layout'
import { Button, Chip, EmptyState, ErrorState, Loading, Toast, VerificationChip, formatDate } from '../components/ui'
import { useAction, useAsync } from '../hooks/useAsync'
import { LANGUAGE_NAME, MOBILITY_OPTIONS, educationLabel, goalLabel, humanizeCode } from '../lib/labels'

function Card({
  icon,
  tone,
  title,
  children,
  wide,
  index,
  action,
}: {
  icon: IconName
  tone?: 'teal' | 'blue' | 'amber'
  title: string
  children: React.ReactNode
  wide?: boolean
  index: number
  action?: React.ReactNode
}) {
  return (
    <section className={`pcard enter ${wide ? 'pcard--wide' : ''}`} style={{ animationDelay: `${index * 60}ms` }} aria-label={title}>
      <header className="pcard__head">
        <span className={`icon-tile icon-tile--sm ${tone ? `icon-tile--${tone}` : ''}`}>
          <Icon name={icon} size={18} />
        </span>
        <h2 className="pcard__title">{title}</h2>
        {action}
      </header>
      <div className="pcard__body">{children}</div>
    </section>
  )
}

export function MyProfile() {
  const navigate = useNavigate()
  const profile = useAsync(() => api.profile(), [])
  const [editTravel, setEditTravel] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const setMobility = useAction(async (mobility: 'low' | 'medium' | 'high') => {
    const updated = await api.patchProfile({ mobility })
    profile.setData(updated)
    await api.generate({ mobility })
    setEditTravel(false)
    setToast('Saved. Your pathways have been re-ranked.')
    return updated
  })

  if (profile.loading) {
    return (
      <Layout>
        <Loading label="Opening your profile…" />
      </Layout>
    )
  }
  if (profile.error || !profile.data) {
    return (
      <Layout>
        <EmptyState
          icon="user"
          title="We don’t know you yet"
          description="Tell us about the work you do — it takes about two minutes, and you can check everything before it’s saved."
          action={
            <Button icon="mic" onClick={() => navigate('/start?mode=voice&fresh=1')}>
              Start talking
            </Button>
          }
        />
      </Layout>
    )
  }

  const p = profile.data
  const skills = p.skills
  const mobility = MOBILITY_OPTIONS.find((o) => o.value === p.mobility)
  let index = 0

  return (
    <Layout>
      <header className="profile-hero">
        <span className="understood-head__avatar" aria-hidden="true">
          {p.display_name.charAt(0).toUpperCase()}
        </span>
        <div className="grow">
          <span className="eyebrow">My profile</span>
          <h1 className="display-2" style={{ margin: '6px 0 8px' }}>
            {p.display_name}
          </h1>
          <div className="row row--tight">
            {p.is_confirmed ? (
              <Chip tone="good" icon="check">
                Confirmed by you {p.confirmed_at ? formatDate(p.confirmed_at) : ''}
              </Chip>
            ) : (
              <Chip tone="warn" icon="alert">
                Not confirmed yet
              </Chip>
            )}
            <Chip icon="globe">{LANGUAGE_NAME[p.preferred_language] ?? p.preferred_language}</Chip>
          </div>
        </div>
        <div className="row">
          <Button variant="secondary" icon="mic" onClick={() => navigate('/start?mode=voice&fresh=1')}>
            Tell us something new
          </Button>
          <Button iconRight="arrowRight" onClick={() => navigate('/skills')}>
            My skills
          </Button>
        </div>
      </header>

      <div className="understood-grid">
        <Card icon="cap" tone="blue" title="Education" index={index++}>
          {p.education ? (
            <>
              <p className="pcard__value">{educationLabel(p.education.level) || p.education.label}</p>
              <VerificationChip status={p.education.verification_status} />
            </>
          ) : (
            <p className="pcard__empty">Not mentioned yet</p>
          )}
        </Card>

        <Card icon="sprout" tone="teal" title="Current work" index={index++}>
          {p.occupations.length === 0 ? (
            <p className="pcard__empty">Not mentioned yet</p>
          ) : (
            <ul className="tag-list">
              {p.occupations.map((o) => (
                <li key={o.id}>
                  <span className="fact-chip">{o.title}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          icon={mobility?.icon ?? 'bus'}
          title="How far you can travel"
          index={index++}
          action={
            <button type="button" className="pcard__edit" aria-pressed={editTravel} onClick={() => setEditTravel((v) => !v)}>
              <Icon name={editTravel ? 'x' : 'edit'} size={14} strokeWidth={2.4} />
              {editTravel ? 'Cancel' : 'Change'}
            </button>
          }
        >
          {editTravel ? (
            <div className="option-grid option-grid--1">
              {MOBILITY_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className="option option--icon"
                  aria-pressed={p.mobility === option.value}
                  disabled={setMobility.pending}
                  onClick={() => setMobility.run(option.value)}
                >
                  <Icon name={option.icon} size={18} /> {option.long}
                </button>
              ))}
            </div>
          ) : (
            <>
              <p className="pcard__value">{mobility?.short}</p>
              <p className="small muted" style={{ margin: 0 }}>
                {p.max_travel_km ? `Up to about ${Math.round(p.max_travel_km)} km` : mobility?.long}
              </p>
            </>
          )}
          {setMobility.error ? <p className="small" style={{ color: 'var(--red-700)' }}>We couldn’t save that. Please try again.</p> : null}
        </Card>

        <Card icon="wrench" tone="teal" title="Skills" wide index={index++}>
          {skills.length === 0 ? (
            <p className="pcard__empty">No skills yet</p>
          ) : (
            <ul className="skill-rows">
              {skills.map((skill) => (
                <li key={skill.id} className="skill-row">
                  <span className="skill-row__mark">
                    <Icon name="check" size={14} strokeWidth={3} />
                  </span>
                  <div className="grow">
                    <div className="skill-row__name">
                      {skill.name}
                      <span className="skill-row__level">
                        {humanizeCode(skill.proficiency)}
                        {skill.years_experience ? ` · ${skill.years_experience} years` : ''}
                      </span>
                    </div>
                    {skill.evidence[0] ? <div className="skill-row__evidence">{skill.evidence[0].description}</div> : null}
                  </div>
                  <VerificationChip status={skill.verification_status} />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card icon="flag" tone="blue" title="Goal" index={index++}>
          {p.goals.length === 0 ? (
            <p className="pcard__empty">Not mentioned yet</p>
          ) : (
            <p className="pcard__value">{p.goals.map((g) => goalLabel(g.goal_type)).join(' · ')}</p>
          )}
          {p.interests.length > 0 ? (
            <p className="pcard__note">
              Interested in <strong>{p.interests.map((i) => i.label.toLowerCase()).join(', ')}</strong> work
            </p>
          ) : null}
        </Card>

        <Card icon="pin" tone="teal" title="Where you are" wide index={index++}>
          {p.location ? (
            <>
              <p className="pcard__value">{p.location.label ?? p.location.village ?? p.location.district}</p>
              <p className="small muted" style={{ margin: 0 }}>
                {[p.location.district, p.location.state, p.location.pincode].filter(Boolean).join(' · ')}
              </p>
            </>
          ) : (
            <p className="pcard__empty">Not shared yet</p>
          )}
          <p className="pcard__note">Used only to measure distance to opportunities.</p>
        </Card>

        {p.constraints.length > 0 ? (
          <Card icon="alert" tone="amber" title="Things to keep in mind" index={index++}>
            <ul className="tag-list">
              {p.constraints.map((c) => (
                <li key={c.id}>
                  <Chip tone="warn">{c.label}</Chip>
                </li>
              ))}
            </ul>
          </Card>
        ) : null}
      </div>

      {setMobility.pending ? <Loading label="Re-ranking your pathways…" /> : null}
      {profile.error ? <ErrorState message="Something went wrong." /> : null}
      <Toast message={toast} onDone={() => setToast(null)} />
    </Layout>
  )
}
