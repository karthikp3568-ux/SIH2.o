/**
 * Screen 4 — pathway detail and explanation.
 *
 * Shows the factor breakdown that produced the score, the competency-level gap,
 * and the provenance of the listing. What it never shows is model reasoning:
 * every line here is derived from a computed number.
 */

import { useNavigate, useParams } from 'react-router-dom'

import { api } from '../api/client'
import { Layout } from '../components/Layout'
import { SkillGapView } from '../components/SkillGapView'
import { Button, Card, Chip, ErrorState, Loading, Meter, Notice, VerificationChip, formatDate } from '../components/ui'
import { useAction, useAsync } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'

export function PathwayDetail() {
  const { recommendationId } = useParams<{ recommendationId: string }>()
  const navigate = useNavigate()
  const { t } = useApp()

  const explanation = useAsync(
    () => (recommendationId ? api.explanation(recommendationId) : Promise.reject(new Error('Missing id'))),
    [recommendationId],
  )

  const choose = useAction(async (pathwayId: string) => {
    await api.selectPathway(pathwayId)
    navigate('/progress')
  })

  if (explanation.loading) {
    return (
      <Layout>
        <Loading label={t('common.loading')} />
      </Layout>
    )
  }
  if (explanation.error || !explanation.data) {
    return (
      <Layout>
        <ErrorState
          message={explanation.error ?? 'Could not load this pathway.'}
          onRetry={explanation.reload}
        />
      </Layout>
    )
  }

  const data = explanation.data
  const evidence = data.evidence ?? {}

  return (
    <Layout>
      <div className="stack">
        <Button variant="ghost" icon="←" onClick={() => navigate('/pathways')}>
          {t('detail.back')}
        </Button>

        <div>
          <h1 style={{ marginBottom: 'var(--space-2)' }}>{data.title}</h1>
          <div className="row">
            <Chip tone="info" icon="◆">
              Match {Math.round(data.match_score * 100)}%
            </Chip>
            {evidence.qualification ? (
              <Chip icon="🎓">
                {evidence.qualification.code ?? evidence.qualification.title}
                {evidence.qualification.nsqf_level ? ` · NSQF ${evidence.qualification.nsqf_level}` : ''}
              </Chip>
            ) : null}
            <VerificationChip status={String(evidence.verification_status ?? 'unverified')} />
          </div>
        </div>

        <Card>
          <h2>{t('detail.whyFits')}</h2>
          <ul className="reason-list">
            {data.why_it_fits.map((reason, index) => (
              <li key={index}>
                <span className="reason-list__icon" aria-hidden="true" style={{ color: 'var(--teal-600)' }}>
                  ✓
                </span>
                <div>
                  <div>{reason.label}</div>
                  {reason.detail ? <div className="tiny muted">{reason.detail}</div> : null}
                </div>
              </li>
            ))}
          </ul>
        </Card>

        {data.what_is_missing.length > 0 ? (
          <Card>
            <h2>{t('detail.whatYouNeed')}</h2>
            <ul className="reason-list">
              {data.what_is_missing.map((reason, index) => (
                <li key={index}>
                  <span className="reason-list__icon" aria-hidden="true" style={{ color: 'var(--amber-700)' }}>
                    ○
                  </span>
                  <div>
                    <div>{reason.label}</div>
                    {reason.detail ? <div className="tiny muted">{reason.detail}</div> : null}
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        ) : null}

        {data.cautions.length > 0 ? (
          <Notice tone="warn" title={t('detail.thingsToCheck')}>
            <ul className="reason-list">
              {data.cautions.map((reason, index) => (
                <li key={index}>
                  <span className="reason-list__icon" aria-hidden="true">
                    !
                  </span>
                  <div>
                    <div className="small">{reason.label}</div>
                    {reason.detail ? <div className="tiny muted">{reason.detail}</div> : null}
                  </div>
                </li>
              ))}
            </ul>
          </Notice>
        ) : null}

        <Card>
          <h2>{t('detail.howScored')}</h2>
          <p className="small muted">{data.method_note}</p>
          <div className="stack-sm" style={{ marginTop: 'var(--space-4)' }}>
            {data.factors.map((factor) => (
              <div key={factor.code}>
                <div className="row row--between" style={{ marginBottom: 4 }}>
                  <span className="small strong">{factor.label}</span>
                  <span className="tiny muted">
                    {Math.round(factor.score * 100)}% × weight {Math.round(factor.weight * 100)}%
                  </span>
                </div>
                <Meter value={factor.score} tone={factor.score >= 0.7 ? 'good' : factor.score < 0.4 ? 'warn' : 'default'} />
              </div>
            ))}
          </div>
        </Card>

        {data.skill_gap_detail ? (
          <Card>
            <h2>{t('detail.whatYouHave')}</h2>
            <SkillGapView report={data.skill_gap_detail} />
          </Card>
        ) : null}

        <Card>
          <h2>{t('detail.source')}</h2>
          <dl className="stack-sm" style={{ margin: 0 }}>
            <div className="row row--between">
              <dt className="small muted">Where this listing came from</dt>
              <dd className="small strong" style={{ margin: 0, textAlign: 'right' }}>
                {String(evidence.source ?? 'unknown')}
              </dd>
            </div>
            <div className="row row--between">
              <dt className="small muted">{t('detail.lastVerified')}</dt>
              <dd className="small strong" style={{ margin: 0 }}>
                {formatDate(evidence.last_verified_at as string | null)}
              </dd>
            </div>
            {evidence.source_url ? (
              <div className="row row--between">
                <dt className="small muted">Link</dt>
                <dd className="small" style={{ margin: 0 }}>
                  <a href={String(evidence.source_url)} target="_blank" rel="noreferrer noopener">
                    Open source
                  </a>
                </dd>
              </div>
            ) : null}
          </dl>
        </Card>

        {data.next_step ? (
          <Card style={{ background: 'var(--blue-050)', borderColor: 'var(--blue-100)' }}>
            <h2>{t('detail.nextStep')}</h2>
            <p>{data.next_step.label}</p>
            <Button
              size="lg"
              icon="✓"
              onClick={() => choose.run(data.pathway_id)}
              loading={choose.pending}
            >
              {t('pathways.choose')}
            </Button>
            {choose.error ? (
              <p className="small" style={{ color: 'var(--red-700)', marginTop: 'var(--space-3)' }}>
                {choose.error}
              </p>
            ) : null}
            <p className="tiny muted" style={{ marginTop: 'var(--space-3)', marginBottom: 0 }}>
              Choosing a pathway records your decision so your progress can be tracked. You can
              change it later.
            </p>
          </Card>
        ) : null}
      </div>
    </Layout>
  )
}
