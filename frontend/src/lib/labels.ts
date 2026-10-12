/**
 * Plain-language vocabulary shared across screens.
 *
 * The backend speaks in codes and bands; the beneficiary should never have to.
 * One place for these words keeps every screen consistent.
 */

import type { IconName } from '../components/Icon'

export const LANGUAGE_NAME: Record<string, string> = {
  en: 'English',
  hi: 'Hindi',
  kn: 'Kannada',
  ta: 'Tamil',
  te: 'Telugu',
  mr: 'Marathi',
  bn: 'Bengali',
  gu: 'Gujarati',
  ml: 'Malayalam',
  pa: 'Punjabi',
  or: 'Odia',
}

export const EDUCATION_OPTIONS = [
  { value: 'none', label: 'No formal schooling' },
  { value: 'primary', label: 'Primary school' },
  { value: 'class_8', label: '8th pass' },
  { value: 'class_10', label: '10th pass' },
  { value: 'class_12', label: '12th pass' },
  { value: 'iti', label: 'ITI' },
  { value: 'diploma', label: 'Diploma' },
  { value: 'graduate', label: 'Graduate' },
]

export function educationLabel(value: string | null | undefined): string {
  if (!value) return ''
  return EDUCATION_OPTIONS.find((o) => o.value === value)?.label ?? value.replace(/_/g, ' ')
}

export const MOBILITY_OPTIONS: { value: 'low' | 'medium' | 'high'; icon: IconName; short: string; long: string }[] = [
  { value: 'low', icon: 'home', short: 'Near home', long: 'Only near my village' },
  { value: 'medium', icon: 'bus', short: 'Nearby town', long: 'I can go to the nearby town' },
  { value: 'high', icon: 'train', short: 'Further away', long: 'I can travel further or move' },
]

export function mobilityLabel(value: string | null | undefined): string {
  return MOBILITY_OPTIONS.find((o) => o.value === value)?.short ?? (value ? String(value) : '')
}

export const BAND_WORD: Record<string, string> = {
  high: 'Strong',
  good: 'Good',
  moderate: 'Fair',
  low: 'Limited',
}

export function matchLabel(score: number): { label: string; tone: 'good' | 'info' | 'warn' } {
  if (score >= 0.72) return { label: 'High match', tone: 'good' }
  if (score >= 0.55) return { label: 'Good match', tone: 'info' }
  return { label: 'Partial match', tone: 'warn' }
}

export const GAP_WORD: Record<string, string> = {
  small: 'A little to learn',
  moderate: 'Some to learn',
  large: 'More to learn',
  unknown: 'Not measured',
}

export const ELIGIBILITY_WORD: Record<string, { label: string; ok: boolean }> = {
  eligible: { label: 'Eligible', ok: true },
  eligible_with_preparation: { label: 'Eligible with preparation', ok: true },
  not_eligible: { label: 'Not eligible', ok: false },
}

export const AVAILABILITY_WORD: Record<string, { label: string; ok: boolean }> = {
  active: { label: 'Open now', ok: true },
  filling_fast: { label: 'Filling fast', ok: true },
  full: { label: 'Full', ok: false },
}

export const GOAL_WORD: Record<string, string> = {
  self_employment: 'Self-employment',
  higher_income: 'Earn more',
  job: 'A steady job',
  wage_employment: 'A steady job',
  apprenticeship: 'An apprenticeship',
  training: 'Get training',
  undecided: 'Still deciding',
}

export function goalLabel(value: string | null | undefined): string {
  if (!value) return ''
  return GOAL_WORD[value] ?? humanizeCode(value)
}

export function humanizeCode(value: string): string {
  const text = value.replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function confidenceWord(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return 'Not stated'
  if (typeof value === 'number') return value >= 0.8 ? 'High' : value >= 0.55 ? 'Medium' : 'Low'
  return humanizeCode(value)
}

export function sourceWord(value: string | null | undefined): string {
  const map: Record<string, string> = {
    self_reported: 'Self-reported',
    inferred: 'Inferred from related skills',
    training: 'From training records',
    assessment: 'From an assessment',
    certification: 'From a certificate',
    admin_verified: 'Verified by staff',
    user_choice: 'You chose this',
  }
  if (!value) return 'Not stated'
  return map[value] ?? humanizeCode(value)
}

export const OUTCOME_WORD: Record<string, string> = {
  recommended: 'Suggested',
  selected: 'Pathway chosen',
  enrolled: 'Enrolled',
  attending: 'Training in progress',
  completed: 'Training completed',
  employed: 'Working',
  self_employed: 'Running own work',
  dropped_out: 'Stopped',
  rejected: 'Not taken up',
  changed_pathway: 'Changed pathway',
  opportunity_inactive: 'Opportunity closed',
}

/** What the beneficiary presses to move to a status — in their words. */
export const OUTCOME_ACTION: Record<string, { label: string; icon: IconName; tone: 'primary' | 'secondary' | 'danger' }> = {
  enrolled: { label: 'I have enrolled', icon: 'check', tone: 'primary' },
  attending: { label: 'My training has started', icon: 'book', tone: 'primary' },
  completed: { label: 'I completed the training', icon: 'cap', tone: 'primary' },
  employed: { label: 'I am now working', icon: 'briefcase', tone: 'primary' },
  self_employed: { label: 'I started my own work', icon: 'store', tone: 'primary' },
  dropped_out: { label: 'I stopped', icon: 'x', tone: 'danger' },
  rejected: { label: 'I did not take this up', icon: 'x', tone: 'danger' },
  changed_pathway: { label: 'I chose a different pathway', icon: 'route', tone: 'secondary' },
  opportunity_inactive: { label: 'It is no longer available', icon: 'alert', tone: 'secondary' },
}

export function possessive(name: string | null | undefined): string {
  if (!name) return 'Your'
  return name.endsWith('s') ? `${name}'` : `${name}'s`
}
