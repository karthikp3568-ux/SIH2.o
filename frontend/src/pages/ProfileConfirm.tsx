/**
 * Screen 2 — "We understood you as…".
 *
 * This screen is the consent gate for the whole system: nothing from the
 * conversation reaches the beneficiary's profile until they press confirm here,
 * and every row can be corrected or removed first.
 */

import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { api } from '../api/client'
import { Layout } from '../components/Layout'
import { Button, Card, Chip, ErrorState, Loading, Notice, VerificationChip } from '../components/ui'
import { useAction } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'
import type { DraftProfile, DraftSkill } from '../api/types'

const MOBILITY_OPTIONS = [
  { value: 'low', icon: '🏠', key: 'mobility.low' },
  { value: 'medium', icon: '🚌', key: 'mobility.medium' },
  { value: 'high', icon: '🚆', key: 'mobility.high' },
]

const EDUCATION_OPTIONS = [
  { value: 'none', label: 'No formal schooling' },
  { value: 'primary', label: 'Primary school' },
  { value: 'class_8', label: '8th standard' },
  { value: 'class_10', label: '10th standard' },
  { value: 'class_12', label: '12th standard' },
  { value: 'iti', label: 'ITI' },
  { value: 'diploma', label: 'Diploma' },
  { value: 'graduate', label: 'Graduate' },
]

function Section({
  icon,
  title,
  children,
  empty,
}: {
  icon: string
  title: string
  children: React.ReactNode
  empty?: boolean
}) {
  return (
    <div style={{ paddingBottom: 'var(--space-4)', borderBottom: '1px solid var(--grey-200)' }}>
      <div className="row" style={{ gap: 'var(--space-2)', marginBottom: 'var(--space-2)' }}>
        <span aria-hidden="true" style={{ fontSize: '1.2rem' }}>
          {icon}
        </span>
        <h3 style={{ margin: 0, fontSize: '1.05rem' }}>{title}</h3>
      </div>
      {empty ? <p className="muted small" style={{ margin: 0 }}>Not mentioned yet</p> : children}
    </div>
  )
}

export function ProfileConfirm() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const navigate = useNavigate()
  const { t } = useApp()

  const [draft, setDraft] = useState<DraftProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [locationText, setLocationText] = useState('')
  const [coords, setCoords] = useState<{ latitude: number; longitude: number; accuracy_m?: number } | null>(null)
  const [geoError, setGeoError] = useState<string | null>(null)
  const [geoPending, setGeoPending] = useState(false)

  useEffect(() => {
    if (!conversationId) return
    api
      .getConversation(conversationId)
      .then((conversation) => {
        setDraft(conversation.draft_profile ?? {})
        const location = conversation.draft_profile?.location as Record<string, any> | undefined
        if (location) {
          setLocationText(String(location.village ?? location.district ?? location.pincode ?? ''))
          if (typeof location.latitude === 'number') {
            setCoords({ latitude: location.latitude, longitude: location.longitude as number })
          }
        }
      })
      .catch((error: Error) => setLoadError(error.message))
      .finally(() => setLoading(false))
  }, [conversationId])

  const confirm = useAction(async () => {
    if (!conversationId || !draft) return undefined
    const locationPayload = coords
      ? { ...coords, source: 'gps' as const }
      : locationText.trim()
        ? /^[1-9]\d{5}$/.test(locationText.trim())
          ? { pincode: locationText.trim(), source: 'pincode_lookup' as const }
          : { village: locationText.trim(), source: 'manual' as const }
        : undefined

    const response = await api.confirmConversation(conversationId, {
      draft_profile: draft,
      location: locationPayload,
      generate_recommendations: true,
    })
    navigate('/pathways', { state: { runId: response.recommendation_run_id } })
    return response
  })

  const useMyLocation = () => {
    if (!('geolocation' in navigator)) {
      setGeoError('This device cannot share its location. Please type your village or PIN code.')
      return
    }
    setGeoPending(true)
    setGeoError(null)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setCoords({
          latitude: Number(position.coords.latitude.toFixed(6)),
          longitude: Number(position.coords.longitude.toFixed(6)),
          accuracy_m: position.coords.accuracy,
        })
        setGeoPending(false)
      },
      () => {
        setGeoError('We could not get your location. Please type your village or PIN code instead.')
        setGeoPending(false)
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 },
    )
  }

  const removeSkill = (code: string) => {
    setDraft((current) =>
      current ? { ...current, skills: (current.skills ?? []).filter((s) => s.code !== code) } : current,
    )
  }

  const setEducation = (value: string) => {
    setDraft((current) =>
      current
        ? {
            ...current,
            education: { value, confidence: 1, evidence: 'You chose this', extractor: 'user_choice' },
          }
        : current,
    )
  }

  const setMobility = (value: string) => {
    setDraft((current) =>
      current
        ? {
            ...current,
            mobility: { value, confidence: 1, evidence: 'You chose this', extractor: 'user_choice' },
          }
        : current,
    )
  }

  if (loading) {
    return (
      <Layout>
        <Loading label={t('common.loading')} />
      </Layout>
    )
  }
  if (loadError || !draft) {
    return (
      <Layout>
        <ErrorState message={loadError ?? 'Could not load your answers.'} onRetry={() => navigate('/')} />
      </Layout>
    )
  }

  const skills = (draft.skills ?? []).filter((s: DraftSkill) => !s.is_category)
  const categories = (draft.skills ?? []).filter((s: DraftSkill) => s.is_category)
  const educationValue = draft.education?.value ? String(draft.education.value) : ''
  const mobilityValue = draft.mobility?.value ? String(draft.mobility.value) : ''

  return (
    <Layout>
      <div className="stack">
        <div>
          <h1>{t('profile.title')}</h1>
          <p className="muted">{t('profile.subtitle')}</p>
        </div>

        <Card className="stack">
          <Section icon="🎓" title={t('profile.education')}>
            <div className="choice-grid grid--3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
              {EDUCATION_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className="choice"
                  aria-pressed={educationValue === option.value}
                  onClick={() => setEducation(option.value)}
                  style={{ minHeight: 52 }}
                >
                  <span>{option.label}</span>
                </button>
              ))}
            </div>
            {draft.education?.evidence ? (
              <p className="tiny muted" style={{ marginTop: 'var(--space-2)', marginBottom: 0 }}>
                {draft.education.evidence}
              </p>
            ) : null}
          </Section>

          <Section icon="🌾" title={t('profile.work')} empty={(draft.occupations ?? []).length === 0}>
            <ul className="tag-list">
              {(draft.occupations ?? []).map((occupation, index) => (
                <li key={index}>
                  <Chip icon="•">{String(occupation.value)}</Chip>
                </li>
              ))}
            </ul>
          </Section>

          <Section icon="🛠️" title={t('profile.skills')} empty={skills.length === 0}>
            <div className="stack-sm">
              {skills.map((skill) => (
                <div
                  key={skill.code}
                  className="row row--between"
                  style={{
                    padding: 'var(--space-3)',
                    background: 'var(--grey-050)',
                    borderRadius: 'var(--radius)',
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div className="row" style={{ gap: 'var(--space-2)' }}>
                      <strong>{skill.name}</strong>
                      <Chip icon="◆">{skill.proficiency}</Chip>
                      <VerificationChip status={skill.verification_status} />
                    </div>
                    <p className="tiny muted" style={{ margin: '4px 0 0' }}>
                      {skill.evidence}
                    </p>
                  </div>
                  <Button
                    variant="danger"
                    onClick={() => removeSkill(skill.code)}
                    aria-label={`Remove ${skill.name}`}
                  >
                    Remove
                  </Button>
                </div>
              ))}
            </div>
            {categories.length > 0 ? (
              <p className="tiny muted" style={{ marginTop: 'var(--space-3)', marginBottom: 0 }}>
                Also noted as areas of work: {categories.map((c) => c.name).join(', ')}
              </p>
            ) : null}
            <Notice tone="info">
              <p className="small" style={{ margin: 0 }}>
                {t('profile.verifiedHint')}
              </p>
            </Notice>
          </Section>

          <Section icon="❤" title={t('profile.interests')} empty={(draft.interests ?? []).length === 0}>
            <ul className="tag-list">
              {(draft.interests ?? []).map((interest, index) => (
                <li key={index}>
                  <Chip icon="•">{String(interest.value).replace('_', ' ')}</Chip>
                </li>
              ))}
            </ul>
          </Section>

          <Section icon="🎯" title={t('profile.goal')} empty={(draft.goals ?? []).length === 0}>
            <ul className="tag-list">
              {(draft.goals ?? []).map((goal, index) => (
                <li key={index}>
                  <Chip tone="info" icon="→">
                    {String(goal.value).replace(/_/g, ' ')}
                  </Chip>
                </li>
              ))}
            </ul>
          </Section>

          <Section icon="🚶" title={t('profile.mobility')}>
            <div className="choice-grid">
              {MOBILITY_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className="choice"
                  aria-pressed={mobilityValue === option.value}
                  onClick={() => setMobility(option.value)}
                >
                  <span className="choice__icon" aria-hidden="true">
                    {option.icon}
                  </span>
                  <span>{t(option.key)}</span>
                </button>
              ))}
            </div>
          </Section>

          <Section icon="📍" title={t('profile.location')}>
            <div className="row" style={{ marginBottom: 'var(--space-3)' }}>
              <Button variant="secondary" icon="📡" onClick={useMyLocation} loading={geoPending}>
                {t('profile.useMyLocation')}
              </Button>
              {coords ? (
                <Chip tone="good" icon="✓">
                  Location captured
                </Chip>
              ) : null}
            </div>
            <label htmlFor="location">{t('profile.enterLocation')}</label>
            <input
              id="location"
              type="text"
              value={locationText}
              onChange={(event) => setLocationText(event.target.value)}
              placeholder="e.g. Wadgaon, or 422103"
              inputMode="text"
            />
            {geoError ? (
              <p className="small" style={{ color: 'var(--amber-700)', marginTop: 'var(--space-2)' }}>
                {geoError}
              </p>
            ) : null}
            <p className="field__hint">
              We use this only to measure distance to opportunities, and to nothing else.
            </p>
          </Section>
        </Card>

        {confirm.error ? <ErrorState message={confirm.error} /> : null}

        <div className="row row--between">
          <Button
            variant="secondary"
            icon="←"
            onClick={() => navigate(`/conversation/${conversationId}`)}
          >
            {t('profile.edit')}
          </Button>
          <Button size="lg" icon="✓" onClick={() => confirm.run()} loading={confirm.pending}>
            {t('profile.confirm')}
          </Button>
        </div>
      </div>
    </Layout>
  )
}
