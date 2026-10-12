/**
 * Where the beneficiary is in the overall journey. Shown at the top of each
 * step so the product reads as one guided path, not a set of pages.
 */

import { Link } from 'react-router-dom'

import { Icon } from './Icon'
import type { IconName } from './Icon'

export type FlowStep = 'talk' | 'confirm' | 'skills' | 'pathways' | 'journey'

const STEPS: { key: FlowStep; label: string; icon: IconName; to?: string }[] = [
  { key: 'talk', label: 'Talk', icon: 'mic' },
  { key: 'confirm', label: 'Confirm', icon: 'user', to: '/profile' },
  { key: 'skills', label: 'Skills', icon: 'graph', to: '/skills' },
  { key: 'pathways', label: 'Pathways', icon: 'route', to: '/pathways' },
  { key: 'journey', label: 'Journey', icon: 'flag', to: '/journey' },
]

export function FlowSteps({ current }: { current: FlowStep }) {
  const index = STEPS.findIndex((s) => s.key === current)
  return (
    <nav className="flow-steps" aria-label="Your progress">
      <ol>
        {STEPS.map((step, i) => {
          const state = i < index ? 'done' : i === index ? 'current' : 'next'
          const content = (
            <>
              <span className="flow-steps__dot">
                <Icon name={state === 'done' ? 'check' : step.icon} size={14} strokeWidth={state === 'done' ? 3 : 2.2} />
              </span>
              <span className="flow-steps__label">{step.label}</span>
            </>
          )
          return (
            <li key={step.key} className={`flow-steps__item is-${state}`} aria-current={state === 'current' ? 'step' : undefined}>
              {state === 'done' && step.to ? <Link to={step.to}>{content}</Link> : <span>{content}</span>}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
