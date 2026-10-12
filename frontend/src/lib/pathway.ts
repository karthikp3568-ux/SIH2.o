/**
 * Plain-language readings of a recommendation.
 *
 * Every phrase here is derived from a field the ranking engine computed —
 * nothing is invented to make a card read better.
 */

import type { Factor, Recommendation } from '../api/types'
import type { IconName } from '../components/Icon'
import { AVAILABILITY_WORD, ELIGIBILITY_WORD, GAP_WORD, mobilityLabel } from './labels'

export function fitReasons(rec: Recommendation, mobility?: string | null): string[] {
  const reasons: string[] = []
  for (const skill of rec.skills_you_have.slice(0, 3)) reasons.push(`${skill.name} experience`)
  if (rec.why_it_fits.some((r) => /want|goal/i.test(r))) reasons.push('Matches what you said you want')
  if (rec.distance_km !== null && rec.distance_km !== undefined) {
    reasons.push(rec.distance_km < 1 ? 'In your own village' : `${Math.round(rec.distance_km)} km from you`)
  }
  if (rec.mobility_fit === 'high' && mobility) reasons.push(`Suits “${mobilityLabel(mobility).toLowerCase()}” travel`)
  return reasons.slice(0, 5)
}

export function gapWord(rec: Recommendation): string {
  return GAP_WORD[rec.skill_gap] ?? GAP_WORD.unknown
}

export function eligibilityWord(rec: Recommendation) {
  return ELIGIBILITY_WORD[rec.eligibility] ?? { label: rec.eligibility.replace(/_/g, ' '), ok: true }
}

export function availabilityWord(rec: Recommendation) {
  return AVAILABILITY_WORD[rec.availability] ?? { label: rec.availability.replace(/_/g, ' '), ok: false }
}

/** A factor score as a word, so the beneficiary never reads a decimal. */
export function strengthWord(score: number): string {
  if (score >= 0.8) return 'Strong'
  if (score >= 0.6) return 'Good'
  if (score >= 0.4) return 'Fair'
  return 'Weak'
}

export function factor(factors: Factor[] | undefined, code: string): Factor | undefined {
  return factors?.find((f) => f.code === code)
}

/** Stable identity for "the same opportunity" across ranking runs. */
export function opportunityKey(rec: Pick<Recommendation, 'title' | 'provider'>): string {
  return `${rec.title}::${rec.provider}`
}

/** What happens after choosing, phrased for the kind of opportunity. */
export function nextSteps(type: string): { title: string; body: string; icon: IconName }[] {
  if (type === 'enterprise' || type === 'self_employment') {
    return [
      { title: 'Register', body: 'Confirm your place with the programme', icon: 'edit' },
      { title: 'Learn the trade side', body: 'Pricing, spares and accounts', icon: 'book' },
      { title: 'Set up', body: 'Tools, a work spot, first customers', icon: 'wrench' },
      { title: 'Get support', body: 'Credit or scheme linkage if eligible', icon: 'shield' },
      { title: 'Start earning', body: 'Run your own service', icon: 'sprout' },
    ]
  }
  if (type === 'job') {
    return [
      { title: 'Apply', body: 'Contact the employer with your details', icon: 'send' },
      { title: 'Interview', body: 'Show the work you already do', icon: 'users' },
      { title: 'Join', body: 'Agree terms and a start date', icon: 'briefcase' },
      { title: 'Learn on the job', body: 'Build the skills still missing', icon: 'book' },
      { title: 'Steady income', body: 'Tell us how it is going', icon: 'sprout' },
    ]
  }
  return [
    { title: 'Enrol', body: 'Confirm the batch date and fee', icon: 'edit' },
    { title: 'Train', body: 'Attend and practise', icon: 'book' },
    { title: 'Complete', body: 'Get assessed and certified', icon: 'cap' },
    { title: 'Find opportunity', body: 'Job or your own service', icon: 'briefcase' },
    { title: 'Start earning', body: 'And tell us how it went', icon: 'sprout' },
  ]
}
