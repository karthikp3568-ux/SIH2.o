/**
 * "Here's what we understood."
 *
 * The consent gate for the whole system: nothing from the conversation reaches
 * the profile until the person confirms here, and every card can be corrected
 * first. This is where AI output stops being a guess and becomes the person's
 * own statement — so each fact shows the words it was heard in.
 */

import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { DraftProfile, DraftSkill, ExtractedFact } from '../api/types'
import { FlowSteps } from '../components/FlowSteps'
import { Icon } from '../components/Icon'
import type { IconName } from '../components/Icon'
import { Layout } from '../components/Layout'
import { Button, Chip, ErrorState, Loading, VerificationChip } from '../components/ui'
import { useAction } from '../hooks/useAsync'
import {
  EDUCATION_OPTIONS,
  LANGUAGE_NAME,
  MOBILITY_OPTIONS,
  educationLabel,
  goalLabel,
  humanizeCode,
} from '../lib/labels'
import { useApp } from '../state/AppContext'

const GOAL_CHOICES = ['self_employment', 'higher_income', 'job', 'apprenticeship', 'training']

const chosen = (value: string): ExtractedFact => ({
  value,
  confidence: 1,
  evidence: 'You chose this',
  extractor: 'user_choice',
})

function ProfileCard({
  icon,
  tone = 'navy',
  title,
  editing,
  onToggle,
  children,
  evidence,
  wide = false,
  index,
  empty,
}: {
  icon: IconName
  tone?: 'navy' | 'teal' | 'blue' | 'amber'
  title: string
  editing?: boolean
  onToggle?: () => void
  children: ReactNode
  evidence?: string | null
  wide?: boolean
  index: number
  empty?: boolean
}) {
  return (
    <section
      className={`pcard enter ${wide ? 'pcard--wide' : ''} ${editing ? 'is-editing' : ''}`}
      style={{ animationDelay: `${index * 70}ms` }}
      aria-label={title}
    >
      <header className="pcard__head">
        <span className={`icon-tile icon-tile--sm ${tone !== 'navy' ? `icon-tile--${tone}` : ''}`}>
          <Icon name={icon} size={18} />
        </span>
        <h2 className="pcard__title">{title}</h2>
        {onToggle ? (
          <button type="button" className="pcard__edit" onClick={onToggle} aria-pressed={editing}>
            <Icon name={editing ? 'check' : 'edit'} size={14} strokeWidth={2.4} />
            {editing ? 'Done' : 'Edit'}
          </button>
        ) : null}
      </header>
      <div className="pcard__body">{empty && !editing ? <p className="pcard__empty">Not mentioned yet</p> : children}</div>
      {evidence && !editing ? (
        <p className="pcard__evidence">
          <Icon name="mic" size={12} /> {evidence}
        </p>
      ) : null}
    </section>
  )
}

export function ProfileConfirm() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const navigate = useNavigate()
  const { user, language } = useApp()

  const [draft, setDraft] = useState<DraftProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [newSkill, setNewSkill] = useState('')
  const [addedSkills, setAddedSkills] = useState<string[]>([])
  const [locationText, setLocationText] = useState('')
  const [coords, setCoords] = useState<{ latitude: number; longitude: number; accuracy_m?: number } | null>(null)
  const [geo, setGeo] = useState<{ pending: boolean; error: string | null }>({ pending: false, error: null })

  useEffect(() => {
    if (!conversationId) return
    api
      .getConversation(conversationId)
      .then((conversation) => {
        setDraft(conversation.draft_profile ?? {})
        const location = conversation.draft_profile?.location as Record<string, any> | undefined
        if (location) {
          setLocationText(String(location.label ?? location.village ?? location.district ?? location.pincode ?? ''))
          if (typeof location.latitude === 'number') setCoords({ latitude: location.latitude, longitude: location.longitude })
        }
      })
      .catch(() => setLoadError('We could not open what you told us.'))
      .finally(() => setLoading(false))
  }, [conversationId])

  const confirm = useAction(async () => {
    if (!conversationId || !draft) return undefined
    const typed = locationText.trim()
    const location = coords
      ? { ...coords, source: 'gps' as const }
      : typed && !draft.location
        ? /^[1-9]\d{5}$/.test(typed)
          ? { pincode: typed, source: 'pincode_lookup' as const }
          : { village: typed, source: 'manual' as const }
        : undefined

    await api.confirmConversation(conversationId, {
      draft_profile: draft,
      location,
      generate_recommendations: addedSkills.length === 0,
    })
    if (addedSkills.length > 0) {
      for (const label of addedSkills) await api.addSkill({ label })
      await api.generate({})
    }
    navigate('/skills')
    return true
  })

  const update = (patch: Partial<DraftProfile>) => setDraft((current) => (current ? { ...current, ...patch } : current))
  const toggle = (key: string) => setEditing((current) => (current === key ? null : key))

  const useMyLocation = () => {
    if (!('geolocation' in navigator)) {
      setGeo({ pending: false, error: 'This device cannot share its location. Type your village or PIN code instead.' })
      return
    }
    setGeo({ pending: true, error: null })
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setCoords({
          latitude: Number(position.coords.latitude.toFixed(6)),
          longitude: Number(position.coords.longitude.toFixed(6)),
          accuracy_m: position.coords.accuracy,
        })
        setGeo({ pending: false, error: null })
      },
      () => setGeo({ pending: false, error: 'We couldn’t detect your location. Type your village or PIN code instead.' }),
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 },
    )
  }

  if (loading) {
    return (
      <Layout>
        <Loading label="Gathering what you told us…" />
      </Layout>
    )
  }
  if (loadError || !draft) {
    return (
      <Layout>
        <ErrorState message={loadError ?? 'We could not open what you told us.'} onRetry={() => navigate('/')} retryLabel="Back to start" />
      </Layout>
    )
  }

  const skills = (draft.skills ?? []).filter((s: DraftSkill) => !s.is_category)
  const areas = (draft.skills ?? []).filter((s: DraftSkill) => s.is_category)
  const education = draft.education?.value ? String(draft.education.value) : ''
  const mobility = draft.mobility?.value ? String(draft.mobility.value) : ''
  const goals = (draft.goals ?? []).map((g) => String(g.value))
  const name = user?.full_name ?? 'You'
  const mobilityMeta = MOBILITY_OPTIONS.find((o) => o.value === mobility)
  let index = 0

  return (
    <Layout>
      <FlowSteps current="confirm" />

      <header className="understood-head">
        <span className="understood-head__avatar" aria-hidden="true">
          {name.charAt(0).toUpperCase()}
        </span>
        <div>
          <span className="eyebrow">Understanding you</span>
          <h1 className="display-2" style={{ margin: '6px 0 8px' }}>
            Here’s what we understood
          </h1>
          <p className="lead" style={{ margin: 0, maxWidth: '58ch' }}>
            Check each card and change anything that’s wrong. Nothing is saved to your profile until you say
            it’s correct.
          </p>
        </div>
      </header>

      <div className="understood-grid">
        <ProfileCard icon="user" title="You" index={index++}>
          <p className="pcard__value">{name}</p>
          <ul className="pcard__meta">
            <li>
              <Icon name="globe" size={14} /> Speaks {LANGUAGE_NAME[language] ?? language}
            </li>
            {draft.age?.value ? (
              <li>
                <Icon name="user" size={14} /> Age {String(draft.age.value)}
              </li>
            ) : null}
            {draft.experience_years?.value ? (
              <li>
                <Icon name="clock" size={14} /> {String(draft.experience_years.value)} years of work experience
              </li>
            ) : draft.experience_years?.label ? (
              // Said without a number ("for several years"); shown as said.
              <li>
                <Icon name="clock" size={14} /> {draft.experience_years.label} of work experience
              </li>
            ) : null}
            {(draft.previous_occupations ?? []).map((occupation) => (
              <li key={String(occupation.value)}>
                <Icon name="clock" size={14} /> Previously: {String(occupation.value).split(' / ')[0]}
              </li>
            ))}
          </ul>
        </ProfileCard>

        <ProfileCard
          icon="cap"
          tone="blue"
          title="Education"
          index={index++}
          editing={editing === 'education'}
          onToggle={() => toggle('education')}
          evidence={draft.education?.evidence}
          empty={!education}
        >
          {editing === 'education' ? (
            <div className="option-grid">
              {EDUCATION_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className="option"
                  aria-pressed={education === option.value}
                  onClick={() => update({ education: chosen(option.value) })}
                >
                  {option.label}
                </button>
              ))}
            </div>
          ) : (
            <p className="pcard__value">{educationLabel(education)}</p>
          )}
        </ProfileCard>

        <ProfileCard
          icon="sprout"
          tone="teal"
          title="Current work"
          index={index++}
          editing={editing === 'work'}
          onToggle={() => toggle('work')}
          evidence={draft.occupations?.[0]?.evidence}
          empty={(draft.occupations ?? []).length === 0}
        >
          <ul className="tag-list">
            {(draft.occupations ?? []).map((occupation, i) => (
              <li key={i}>
                <span className="fact-chip">
                  {String(occupation.value)}
                  {editing === 'work' ? (
                    <button
                      type="button"
                      aria-label={`Remove ${String(occupation.value)}`}
                      onClick={() => update({ occupations: (draft.occupations ?? []).filter((_, j) => j !== i) })}
                    >
                      <Icon name="x" size={13} strokeWidth={2.6} />
                    </button>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </ProfileCard>

        <ProfileCard
          icon="wrench"
          tone="teal"
          title="Skills"
          wide
          index={index++}
          editing={editing === 'skills'}
          onToggle={() => toggle('skills')}
          empty={skills.length === 0 && addedSkills.length === 0}
        >
          <ul className="skill-rows">
            {skills.map((skill, i) => (
              <li key={skill.code} className="skill-row pop" style={{ animationDelay: `${300 + i * 160}ms` }}>
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
                  <div className="skill-row__evidence">“{skill.raw_label}” — {skill.evidence}</div>
                </div>
                <VerificationChip status={skill.verification_status} />
                {editing === 'skills' ? (
                  <Button
                    variant="danger"
                    size="sm"
                    icon="x"
                    onClick={() => update({ skills: (draft.skills ?? []).filter((s) => s.code !== skill.code) })}
                    aria-label={`Remove ${skill.name}`}
                  >
                    Remove
                  </Button>
                ) : null}
              </li>
            ))}
            {addedSkills.map((label) => (
              <li key={label} className="skill-row pop">
                <span className="skill-row__mark skill-row__mark--new">
                  <Icon name="plus" size={14} strokeWidth={3} />
                </span>
                <div className="grow">
                  <div className="skill-row__name">{label}</div>
                  <div className="skill-row__evidence">You added this — we’ll match it to a known skill when you confirm.</div>
                </div>
                {editing === 'skills' ? (
                  <Button variant="danger" size="sm" icon="x" onClick={() => setAddedSkills((list) => list.filter((l) => l !== label))}>
                    Remove
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
          {editing === 'skills' ? (
            <form
              className="add-row"
              onSubmit={(event) => {
                event.preventDefault()
                const label = newSkill.trim()
                if (label && !addedSkills.includes(label)) setAddedSkills((list) => [...list, label])
                setNewSkill('')
              }}
            >
              <label htmlFor="new-skill" className="visually-hidden">
                Add a skill
              </label>
              <input
                id="new-skill"
                type="text"
                value={newSkill}
                onChange={(event) => setNewSkill(event.target.value)}
                placeholder="Add something you can do, e.g. welding"
              />
              <Button type="submit" variant="secondary" icon="plus" disabled={!newSkill.trim()}>
                Add
              </Button>
            </form>
          ) : null}
          {areas.length > 0 ? (
            <p className="pcard__note">
              Also noted as areas of your work: <strong>{areas.map((a) => a.name).join(', ')}</strong>
            </p>
          ) : null}
        </ProfileCard>

        <ProfileCard
          icon="target"
          tone="amber"
          title="Interests"
          index={index++}
          editing={editing === 'interests'}
          onToggle={() => toggle('interests')}
          evidence={draft.interests?.[0]?.evidence}
          empty={(draft.interests ?? []).length === 0}
        >
          <ul className="tag-list">
            {(draft.interests ?? []).map((interest, i) => (
              <li key={i}>
                <span className="fact-chip">
                  {humanizeCode(String(interest.value))} work
                  {editing === 'interests' ? (
                    <button
                      type="button"
                      aria-label={`Remove ${String(interest.value)}`}
                      onClick={() => update({ interests: (draft.interests ?? []).filter((_, j) => j !== i) })}
                    >
                      <Icon name="x" size={13} strokeWidth={2.6} />
                    </button>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </ProfileCard>

        <ProfileCard
          icon="flag"
          tone="blue"
          title="Goal"
          index={index++}
          editing={editing === 'goal'}
          onToggle={() => toggle('goal')}
          evidence={draft.goals?.[0]?.evidence}
          empty={goals.length === 0}
        >
          {editing === 'goal' ? (
            <div className="option-grid">
              {GOAL_CHOICES.map((value) => (
                <button
                  key={value}
                  type="button"
                  className="option"
                  aria-pressed={goals.includes(value)}
                  onClick={() =>
                    update({
                      goals: goals.includes(value)
                        ? (draft.goals ?? []).filter((g) => String(g.value) !== value)
                        : [...(draft.goals ?? []), chosen(value)],
                    })
                  }
                >
                  {goalLabel(value)}
                </button>
              ))}
            </div>
          ) : (
            <p className="pcard__value">{goals.map(goalLabel).join(' · ')}</p>
          )}
        </ProfileCard>

        <ProfileCard
          icon={mobilityMeta?.icon ?? 'bus'}
          title="How far you can travel"
          index={index++}
          editing={editing === 'travel'}
          onToggle={() => toggle('travel')}
          evidence={draft.mobility?.evidence}
          empty={!mobility}
        >
          {editing === 'travel' ? (
            <div className="option-grid option-grid--1">
              {MOBILITY_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className="option option--icon"
                  aria-pressed={mobility === option.value}
                  onClick={() => update({ mobility: chosen(option.value) })}
                >
                  <Icon name={option.icon} size={18} /> {option.long}
                </button>
              ))}
            </div>
          ) : (
            <>
              <p className="pcard__value">{mobilityMeta?.short}</p>
              <p className="small muted" style={{ margin: 0 }}>
                {mobilityMeta?.long}
              </p>
            </>
          )}
        </ProfileCard>

        <ProfileCard icon="pin" tone="teal" title="Where you are" index={index++} wide>
          {draft.location ? (
            <div className="row">
              <p className="pcard__value grow" style={{ margin: 0 }}>
                {locationText || 'Location shared'}
              </p>
              <Chip tone="good" icon="check">
                Location known
              </Chip>
            </div>
          ) : null}
          {!draft.location ? (
            <div className="location-row">
              <Button variant="secondary" icon="pin" onClick={useMyLocation} loading={geo.pending}>
                Use my location
              </Button>
              <span className="muted small">or</span>
              <div className="grow">
                <label htmlFor="location" className="visually-hidden">
                  Village or PIN code
                </label>
                <input
                  id="location"
                  type="text"
                  value={locationText}
                  onChange={(event) => setLocationText(event.target.value)}
                  placeholder="Type your village or PIN code"
                />
              </div>
              {coords ? (
                <Chip tone="good" icon="check">
                  Location captured
                </Chip>
              ) : null}
            </div>
          ) : null}
          {geo.error ? (
            <p className="small" role="alert" style={{ color: 'var(--amber-700)', margin: '8px 0 0' }}>
              {geo.error}
            </p>
          ) : null}
          <p className="pcard__note">We use your location only to measure distance to opportunities.</p>
        </ProfileCard>
      </div>

      {confirm.error ? (
        <div style={{ marginTop: 'var(--space-5)' }}>
          <ErrorState title="We couldn’t save this" message="Please try again in a moment. Nothing you changed has been lost." />
        </div>
      ) : null}

      <div className="confirm-dock" role="region" aria-label="Confirm your profile">
        <div className="confirm-dock__inner">
          <div className="grow">
            <strong>Is this correct?</strong>
            <span className="small muted"> You can change it again later.</span>
          </div>
          <Button variant="secondary" icon="mic" onClick={() => navigate(`/conversation/${conversationId}`)}>
            Keep talking
          </Button>
          <Button size="lg" icon="check" onClick={() => confirm.run()} loading={confirm.pending}>
            Yes, continue
          </Button>
        </div>
      </div>
    </Layout>
  )
}
