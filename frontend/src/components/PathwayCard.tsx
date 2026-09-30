import type { Recommendation } from '../api/types'
import { useApp } from '../state/AppContext'
import { Chip, VerificationChip, daysAgo } from './ui'

const TYPE_ICON: Record<string, string> = {
  training: '📘',
  apprenticeship: '🛠️',
  job: '💼',
  enterprise: '🏪',
  self_employment: '🏪',
}

const FIT_TONE: Record<string, 'good' | 'info' | 'warn' | 'neutral'> = {
  high: 'good',
  good: 'good',
  moderate: 'info',
  low: 'warn',
}

export function PathwayCard({
  recommendation,
  onOpen,
}: {
  recommendation: Recommendation
  onOpen: (recommendation: Recommendation) => void
}) {
  const { t } = useApp()
  const gapKey = `gap.${recommendation.skill_gap}`
  const fitKey = `band.${recommendation.skill_fit}`

  return (
    <button
      type="button"
      className={`card pathway-card ${recommendation.rank === 1 ? 'pathway-card--top' : ''}`}
      onClick={() => onOpen(recommendation)}
      aria-label={`${recommendation.title}. ${t('pathways.viewDetail')}`}
    >
      <div className="card__header">
        <div className="row" style={{ gap: 'var(--space-3)', flex: 1, minWidth: 0 }}>
          <span className="card__rank" aria-hidden="true">
            {recommendation.rank}
          </span>
          <div style={{ minWidth: 0 }}>
            <h3 style={{ marginBottom: 2 }}>
              <span aria-hidden="true" style={{ marginRight: 6 }}>
                {TYPE_ICON[recommendation.opportunity_type] ?? '•'}
              </span>
              {recommendation.title}
            </h3>
            <p className="small muted" style={{ margin: 0 }}>
              {recommendation.provider}
              {recommendation.location_label ? ` · ${recommendation.location_label}` : ''}
            </p>
          </div>
        </div>
        {recommendation.is_selected ? <Chip tone="good" icon="✓">{t('pathways.chosen')}</Chip> : null}
      </div>

      <ul className="tag-list" style={{ marginBottom: 'var(--space-3)' }}>
        <li>
          <Chip tone={FIT_TONE[recommendation.skill_fit] ?? 'neutral'} icon="◆">
            {t('pathways.match')}: {t(fitKey)}
          </Chip>
        </li>
        {recommendation.distance_km !== null ? (
          <li>
            <Chip icon="📍">
              {Math.round(recommendation.distance_km)} {t('pathways.km')}
            </Chip>
          </li>
        ) : null}
        <li>
          <Chip
            tone={recommendation.skill_gap === 'small' ? 'good' : recommendation.skill_gap === 'moderate' ? 'warn' : 'bad'}
            icon="◎"
          >
            {t('pathways.skillGap')}: {t(gapKey)}
          </Chip>
        </li>
        <li>
          <Chip tone={recommendation.availability === 'active' ? 'good' : 'warn'} icon="●">
            {recommendation.availability === 'active'
              ? t('common.active')
              : recommendation.availability === 'filling_fast'
                ? 'Filling fast'
                : recommendation.availability}
          </Chip>
        </li>
      </ul>

      {recommendation.why_it_fits.length > 0 ? (
        <div style={{ marginBottom: 'var(--space-3)' }}>
          <p className="small strong" style={{ marginBottom: 4 }}>
            {t('pathways.whyFits')}
          </p>
          <ul className="reason-list">
            {recommendation.why_it_fits.slice(0, 3).map((reason, index) => (
              <li key={index}>
                <span className="reason-list__icon" aria-hidden="true">
                  ✓
                </span>
                <span className="small">{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {recommendation.skill_gaps.length > 0 ? (
        <p className="small" style={{ marginBottom: 'var(--space-3)' }}>
          <span className="strong">{t('pathways.needNext')}: </span>
          <span className="muted">{recommendation.skill_gaps.slice(0, 3).join(', ')}</span>
        </p>
      ) : null}

      <div className="row row--between tiny muted">
        <span className="row" style={{ gap: 6 }}>
          <VerificationChip status={recommendation.verification_status} />
          <span>checked {daysAgo(recommendation.last_verified_at)}</span>
        </span>
        <span className="strong" style={{ color: 'var(--blue-600)' }}>
          {t('pathways.viewDetail')} →
        </span>
      </div>
    </button>
  )
}
