/**
 * Staff console.
 *
 * The governing idea: an AI recommendation is a proposal. Staff verify the
 * data behind it, review the profile that produced it, and accept, edit or
 * reject the recommendation itself — every action lands in the audit trail.
 */

import { useParams } from 'react-router-dom'

import { AdminLayout } from '../../components/Layout'
import { EmptyState, Button } from '../../components/ui'
import { Layout } from '../../components/Layout'
import { useAsync } from '../../hooks/useAsync'
import { loadReviewQueue } from '../../lib/adminData'
import { useApp } from '../../state/AppContext'
import { AuditTrail } from './AuditTrail'
import { Beneficiaries } from './Beneficiaries'
import { Opportunities } from './Opportunities'
import { Outcomes } from './Outcomes'
import { Overview } from './Overview'
import { ReviewQueue } from './ReviewQueue'

const TITLES: Record<string, string> = {
  overview: 'Overview',
  beneficiaries: 'Beneficiaries',
  opportunities: 'Opportunities',
  recommendations: 'AI review queue',
  outcomes: 'Outcomes',
  verification: 'Verification',
  audit: 'Audit trail',
}

export function AdminConsole() {
  const { section = 'overview' } = useParams<{ section?: string }>()
  const { isAdmin, user } = useApp()
  const queue = useAsync(() => (isAdmin ? loadReviewQueue() : Promise.resolve(null)), [isAdmin])

  if (!isAdmin) {
    return (
      <Layout>
        <EmptyState
          icon="lock"
          title="Staff access only"
          description="Sign in with an administrator or counsellor account to open the console."
          action={<Button onClick={() => window.location.assign('/signin?as=admin')}>Staff sign in</Button>}
        />
      </Layout>
    )
  }

  const title = TITLES[section] ?? 'Overview'

  return (
    <AdminLayout
      title={title}
      reviewCount={queue.data?.pendingCount}
      actions={<span className="small muted">Signed in as {user?.email}</span>}
    >
      {section === 'overview' ? <Overview queue={queue.data} /> : null}
      {section === 'beneficiaries' ? <Beneficiaries /> : null}
      {section === 'opportunities' ? <Opportunities mode="all" /> : null}
      {section === 'verification' ? <Opportunities mode="verification" /> : null}
      {section === 'recommendations' ? <ReviewQueue queue={queue} /> : null}
      {section === 'outcomes' ? <Outcomes /> : null}
      {section === 'audit' ? <AuditTrail /> : null}
      {!TITLES[section] ? <EmptyState icon="compass" title="Nothing here" description="That section does not exist." /> : null}
    </AdminLayout>
  )
}
