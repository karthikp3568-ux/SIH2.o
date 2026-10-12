/**
 * "Why this pathway?"
 *
 * The explanation is assembled by the backend from the same factor scores
 * that produced the ranking — it is not generated prose. The beneficiary sees
 * reasons and gaps in words only; factor weights stay in the staff console.
 */

import { useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import type { Recommendation } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { matchLabel } from '../lib/labels'
import { Icon } from './Icon'
import { Button, Drawer, Loading, TrustBadge } from './ui'

export function WhyThisPanel({ rec, onClose }: { rec: Recommendation | null; onClose: () => void }) {
  const navigate = useNavigate()
  const explanation = useAsync(() => (rec ? api.explanation(rec.id) : Promise.resolve(null)), [rec?.id])
  const data = explanation.data
  const match = rec ? matchLabel(rec.match_score) : null

  return (
    <Drawer
      open={rec !== null}
      onClose={onClose}
      eyebrow={
        <>
          <Icon name="info" size={13} /> Why this pathway?
        </>
      }
      title={rec?.qualification?.title ?? rec?.title ?? ''}
      footer={
        rec ? (
          <>
            <Button iconRight="arrowRight" onClick={() => navigate(`/pathway/${rec.id}`)}>
              View full pathway
            </Button>
            <Button variant="ghost" onClick={onClose}>
              Close
            </Button>
          </>
        ) : null
      }
    >
      {explanation.loading ? <Loading label="Gathering the reasons…" /> : null}
      {explanation.error ? (
        <p className="small" role="alert">
          We couldn’t load the explanation right now. Please try again.
        </p>
      ) : null}

      {rec && data ? (
        <div className="why">
          <div className={`why__match match-pill match-pill--${match!.tone}`}>
            <Icon name="sparkle" size={15} /> {match!.label}
            <span className="why__match-sub">for {rec.provider}</span>
          </div>

          <section>
            <h3 className="why__title why__title--have">
              <Icon name="checkCircle" size={18} /> Why this matches
            </h3>
            <ul className="check-list">
              {data.why_it_fits.map((reason, i) => (
                <li key={i} className="enter" style={{ animationDelay: `${i * 60}ms` }}>
                  <span className="check-list__mark check-list__mark--have">
                    <Icon name="check" size={13} strokeWidth={3} />
                  </span>
                  <div>
                    <div className="strong">{reason.label}</div>
                    {reason.detail ? <div className="check-list__detail">{reason.detail}</div> : null}
                  </div>
                </li>
              ))}
              <li>
                <span className="check-list__mark check-list__mark--have">
                  <Icon name="check" size={13} strokeWidth={3} />
                </span>
                <div>
                  <div className="strong">Currently available</div>
                  <div className="check-list__detail">
                    <TrustBadge verificationStatus={rec.verification_status} lastVerifiedAt={rec.last_verified_at} validUntil={rec.valid_until} />
                  </div>
                </div>
              </li>
            </ul>
          </section>

          {data.what_is_missing.length > 0 ? (
            <section>
              <h3 className="why__title why__title--need">
                <Icon name="target" size={18} /> What is missing
              </h3>
              <ul className="check-list">
                {data.what_is_missing.map((reason, i) => (
                  <li key={i}>
                    <span className="check-list__mark check-list__mark--need" aria-hidden="true" />
                    <div>
                      <div className="strong">{reason.label}</div>
                      {reason.detail ? <div className="check-list__detail">{reason.detail}</div> : null}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {data.cautions.length > 0 ? (
            <section>
              <h3 className="why__title why__title--warn">
                <Icon name="alert" size={18} /> Things to check
              </h3>
              <ul className="check-list">
                {data.cautions.map((reason, i) => (
                  <li key={i}>
                    <span className="check-list__mark check-list__mark--warn">
                      <Icon name="alert" size={12} strokeWidth={2.6} />
                    </span>
                    <div>
                      <div className="strong">{reason.label}</div>
                      {reason.detail ? <div className="check-list__detail">{reason.detail}</div> : null}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {data.next_step ? (
            <section className="why__next">
              <div className="eyebrow">
                <Icon name="flag" size={13} /> Next step
              </div>
              <p>{data.next_step.label}</p>
            </section>
          ) : null}

        </div>
      ) : null}
    </Drawer>
  )
}
