/**
 * One recommended pathway.
 *
 * The match is shown as a band ("High match"), never as a percentage: the
 * score is a weighted average of product-judgement weights, and a decimal
 * would imply a precision it does not have.
 */

import type { Recommendation } from '../api/types'
import { matchLabel } from '../lib/labels'
import { availabilityWord, fitReasons } from '../lib/pathway'
import { Icon, OPPORTUNITY_TYPE } from './Icon'
import { Button, Chip, TrustBadge } from './ui'

export function PathwayCard({
  rec,
  mobility,
  index,
  movedFrom,
  highlighted,
  onWhy,
  onOpen,
  onHover,
}: {
  rec: Recommendation
  mobility?: string | null
  index: number
  /** Rank in the previous run, when it changed. */
  movedFrom?: number | null
  highlighted?: boolean
  onWhy: () => void
  onOpen: () => void
  onHover?: (hovering: boolean) => void
}) {
  const type = OPPORTUNITY_TYPE[rec.opportunity_type] ?? { icon: 'briefcase', label: rec.opportunity_type }
  const match = matchLabel(rec.match_score)
  const availability = availabilityWord(rec)
  const reasons = fitReasons(rec, mobility)
  const top = rec.rank === 1
  const moved = movedFrom && movedFrom !== rec.rank ? movedFrom - rec.rank : 0

  return (
    <article
      className={`path-card enter ${top ? 'path-card--top' : ''} ${highlighted ? 'is-highlighted' : ''}`}
      style={{ animationDelay: `${index * 120}ms` }}
      onMouseEnter={() => onHover?.(true)}
      onMouseLeave={() => onHover?.(false)}
      aria-labelledby={`path-${rec.id}`}
    >
      <div className="path-card__top">
        <span className="path-card__rank" aria-label={`Rank ${rec.rank}`}>
          {rec.rank}
        </span>
        {top ? <span className="path-card__ribbon">Strongest fit</span> : null}
        {moved !== 0 ? (
          <span className={`path-card__moved ${moved > 0 ? 'is-up' : 'is-down'}`}>
            <Icon name={moved > 0 ? 'arrowUp' : 'arrowDown'} size={13} strokeWidth={2.6} />
            {moved > 0 ? `Up from #${movedFrom}` : `Down from #${movedFrom}`}
          </span>
        ) : null}
        {rec.is_selected ? (
          <Chip tone="good" icon="check">
            You chose this
          </Chip>
        ) : null}
      </div>

      <div className="path-card__head">
        <span className="icon-tile icon-tile--lg path-card__type">
          <Icon name={type.icon} size={26} />
        </span>
        <div className="grow">
          <span className="eyebrow">{type.label}</span>
          <h3 id={`path-${rec.id}`} className="path-card__title">
            {rec.qualification?.title ?? rec.title}
          </h3>
          <p className="path-card__provider">
            {rec.provider}
            {rec.location_label ? ` · ${rec.location_label}` : ''}
          </p>
        </div>
      </div>

      <ul className="path-card__facts">
        <li className={`match-pill match-pill--${match.tone}`}>
          <Icon name="sparkle" size={14} strokeWidth={2.4} /> {match.label}
        </li>
        {rec.distance_km !== null ? (
          <li>
            <Icon name="pin" size={15} /> {rec.distance_km < 1 ? 'In your village' : `${Math.round(rec.distance_km)} km away`}
          </li>
        ) : null}
        {rec.qualification?.nsqf_level ? (
          <li>
            <Icon name="cap" size={15} /> NSQF level {rec.qualification.nsqf_level}
          </li>
        ) : null}
        <li className={availability.ok ? 'is-ok' : 'is-warn'}>
          <Icon name={availability.ok ? 'checkCircle' : 'alert'} size={15} /> {availability.label}
          {rec.seats_available ? ` · ${rec.seats_available} seats` : ''}
        </li>
      </ul>

      <div className="path-card__body">
        <div>
          <h4 className="path-card__label">Why it fits</h4>
          <ul className="check-list">
            {reasons.map((reason) => (
              <li key={reason}>
                <span className="check-list__mark check-list__mark--have">
                  <Icon name="check" size={13} strokeWidth={3} />
                </span>
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </div>
        {rec.missing_competencies.length > 0 ? (
          <div>
            <h4 className="path-card__label">Skills to build</h4>
            <ul className="tag-list">
              {rec.missing_competencies.slice(0, 3).map((c) => (
                <li key={c.code}>
                  <span className="need-chip">{c.name}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div>
            <h4 className="path-card__label">Skills to build</h4>
            <p className="small muted" style={{ margin: 0 }}>
              None — you already cover what this needs.
            </p>
          </div>
        )}
      </div>

      <footer className="path-card__foot">
        <TrustBadge verificationStatus={rec.verification_status} lastVerifiedAt={rec.last_verified_at} validUntil={rec.valid_until} />
        <div className="row row--tight">
          <Button variant="ghost" icon="info" onClick={onWhy}>
            Why this?
          </Button>
          <Button variant={top ? 'primary' : 'secondary'} iconRight="arrowRight" onClick={onOpen}>
            View pathway
          </Button>
        </div>
      </footer>
    </article>
  )
}
