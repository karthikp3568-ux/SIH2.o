/** Loaders for the staff console. */

import { api } from '../api/client'
import type { Recommendation, RecommendationRun } from '../api/types'

export interface BeneficiaryRow {
  id: string
  display_name: string
  preferred_language: string
  mobility: string
  is_confirmed: boolean
  skill_count: number
  goals: string[]
  district: string | null
  created_at: string
}

export interface ReviewItem {
  beneficiary: BeneficiaryRow
  run: RecommendationRun
  pending: Recommendation[]
}

export interface ReviewQueueData {
  beneficiaries: BeneficiaryRow[]
  items: ReviewItem[]
  pendingCount: number
}

/**
 * Every AI recommendation a human has not yet accepted, edited or rejected,
 * grouped by beneficiary. The data set is small (a district's caseload), so a
 * call per beneficiary is acceptable; a production build would add a queue
 * endpoint.
 */
export async function loadReviewQueue(): Promise<ReviewQueueData> {
  const beneficiaries = (await api.adminBeneficiaries()) as BeneficiaryRow[]
  const runs = await Promise.all(
    beneficiaries.filter((b) => b.is_confirmed).map((b) => api.adminRecommendations(b.id).then((run) => ({ b, run })).catch(() => null)),
  )
  const items = runs
    .filter((entry): entry is { b: BeneficiaryRow; run: RecommendationRun } => entry !== null)
    .map(({ b, run }) => ({ beneficiary: b, run, pending: run.recommendations.filter((r) => !r.is_overridden) }))
  return { beneficiaries, items, pendingCount: items.reduce((sum, item) => sum + item.pending.length, 0) }
}
