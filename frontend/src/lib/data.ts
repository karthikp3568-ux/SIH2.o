/** Loaders shared by the beneficiary screens. */

import { api, ApiError } from '../api/client'
import type { BeneficiaryProfile, RecommendationRun } from '../api/types'

/**
 * The beneficiary's profile and their most recent recommendation run. If no
 * run exists yet (profile confirmed elsewhere, or data was reset) one is
 * generated so the screen never dead-ends.
 */
export async function loadMyRun(): Promise<{ profile: BeneficiaryProfile; run: RecommendationRun }> {
  const profile = await api.profile()
  let run: RecommendationRun
  try {
    run = await api.latestRun(profile.id)
  } catch (error) {
    if (error instanceof ApiError && error.status !== 404) throw error
    run = await api.generate({})
  }
  return { profile, run }
}
