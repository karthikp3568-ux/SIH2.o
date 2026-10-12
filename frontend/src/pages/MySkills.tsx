/**
 * My Skills — the skill graph and the skill gap.
 *
 * This is the screen that shows the innovation: what the person said, turned
 * into skills, the credit those skills give towards related work, and exactly
 * which competencies stand between them and a recognised qualification.
 */

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import { FlowSteps } from '../components/FlowSteps'
import { Layout } from '../components/Layout'
import { SkillGapCard } from '../components/SkillGapCard'
import { SkillGraph } from '../components/SkillGraph'
import { Button, EmptyState, ErrorState, Loading } from '../components/ui'
import { useAsync } from '../hooks/useAsync'
import { loadMyRun } from '../lib/data'
import { possessive } from '../lib/labels'

export function MySkills() {
  const navigate = useNavigate()
  const data = useAsync(async () => {
    const [{ profile, run }, gap] = await Promise.all([loadMyRun(), api.skillGap({ limit: 3 })])
    return { profile, run, gap }
  }, [])
  const [targetId, setTargetId] = useState<string | null>(null)

  const reports = data.data?.gap.reports ?? []
  const topQualification = data.data?.run.recommendations[0]?.qualification?.id

  useEffect(() => {
    if (targetId || reports.length === 0) return
    setTargetId(reports.find((r) => r.qualification_id === topQualification)?.qualification_id ?? reports[0].qualification_id)
  }, [reports, targetId, topQualification])

  const target = useMemo(() => reports.find((r) => r.qualification_id === targetId) ?? null, [reports, targetId])
  const matchingRec = data.data?.run.recommendations.find((r) => r.qualification?.id === targetId)

  if (data.loading) {
    return (
      <Layout>
        <Loading label="Building your skill graph…" />
      </Layout>
    )
  }
  if (data.error || !data.data) {
    return (
      <Layout>
        <ErrorState
          title="We couldn’t build your skill graph"
          message="This usually means your profile is not confirmed yet. Talk to us first, then come back."
          onRetry={data.reload}
        >
          <Button variant="ghost" size="sm" onClick={() => navigate('/start?mode=voice')}>
            Start talking
          </Button>
        </ErrorState>
      </Layout>
    )
  }

  const { profile, run, gap } = data.data
  const firstName = profile.display_name.split(' ')[0]
  const pathwayCount = run.recommendations.length

  return (
    <Layout>
      <FlowSteps current="skills" />

      <header className="page-head page-head--split">
        <div>
          <span className="eyebrow">Skill graph</span>
          <h1>{possessive(firstName)} skill profile</h1>
          <p className="lead" style={{ maxWidth: '60ch' }}>
            Built only from what you told us. Select any skill to see where it came from — nothing here is
            treated as proven until someone verifies it.
          </p>
        </div>
        {reports.length > 1 ? (
          <div className="target-picker">
            <span className="eyebrow">Compare against</span>
            <div className="segmented segmented--stack" role="group" aria-label="Qualification to compare against">
              {reports.map((report) => (
                <button
                  key={report.qualification_id}
                  type="button"
                  aria-pressed={report.qualification_id === targetId}
                  onClick={() => setTargetId(report.qualification_id)}
                >
                  {report.qualification_title}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </header>

      <div className="card card--raised graph-card">
        <SkillGraph graph={gap.skill_graph} name={profile.display_name} target={target} />
      </div>

      <section className="closer" aria-labelledby="closer-heading">
        <div className="closer__intro">
          <h2 id="closer-heading" className="display-2">
            You’re closer than you think.
          </h2>
          <p className="lead">
            Your work already covers part of a recognised standard. Here is what counts, and the few skills
            left to build.
          </p>
        </div>

        {target ? (
          <SkillGapCard
            report={target}
            nextStep={matchingRec?.next_step}
            action={
              matchingRec ? (
                <Button variant="secondary" iconRight="arrowRight" onClick={() => navigate(`/pathway/${matchingRec.id}`)}>
                  View this pathway
                </Button>
              ) : null
            }
          />
        ) : (
          <EmptyState
            icon="target"
            title="No standard to compare against yet"
            description="Once pathways are found for you, we’ll show how close you are to each one."
          />
        )}
      </section>

      <div className="next-bar">
        <div className="grow">
          <strong>
            {pathwayCount > 0
              ? `${pathwayCount} pathway${pathwayCount === 1 ? '' : 's'} fit your profile`
              : 'See what is available near you'}
          </strong>
          <div className="small muted">Ranked on your skills, your goal, and how far you can travel.</div>
        </div>
        <Button size="lg" iconRight="arrowRight" onClick={() => navigate('/pathways')}>
          See pathways
        </Button>
      </div>
    </Layout>
  )
}
