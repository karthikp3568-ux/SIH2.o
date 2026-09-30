/**
 * Small shared UI primitives.
 *
 * Every status indicator pairs an icon and a word with its colour, so meaning
 * never depends on colour perception alone.
 */

import type { ButtonHTMLAttributes, ReactNode } from 'react'

export function Card({
  children,
  className = '',
  ...rest
}: { children: ReactNode; className?: string } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`card ${className}`} {...rest}>
      {children}
    </div>
  )
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'md' | 'lg'
  block?: boolean
  loading?: boolean
  icon?: string
}

export function Button({
  variant = 'primary',
  size = 'md',
  block = false,
  loading = false,
  icon,
  children,
  className = '',
  disabled,
  ...rest
}: ButtonProps) {
  const classes = [
    'btn',
    variant !== 'primary' ? `btn--${variant}` : '',
    size === 'lg' ? 'btn--lg' : '',
    block ? 'btn--block' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button className={classes} disabled={disabled || loading} {...rest}>
      {loading ? <span className="spinner" aria-hidden="true" /> : icon ? <span aria-hidden="true">{icon}</span> : null}
      {children}
    </button>
  )
}

export type ChipTone = 'neutral' | 'good' | 'info' | 'warn' | 'bad'

export function Chip({
  tone = 'neutral',
  icon,
  children,
  title,
}: {
  tone?: ChipTone
  icon?: string
  children: ReactNode
  title?: string
}) {
  return (
    <span className={`chip ${tone !== 'neutral' ? `chip--${tone}` : ''}`} title={title}>
      {icon ? (
        <span className="chip__icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      {children}
    </span>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="row" role="status" aria-live="polite" style={{ padding: 'var(--space-5)' }}>
      <span className="spinner" aria-hidden="true" />
      <span className="muted">{label}</span>
    </div>
  )
}

export function ErrorState({
  message,
  onRetry,
  retryLabel = 'Try again',
}: {
  message: string
  onRetry?: () => void
  retryLabel?: string
}) {
  return (
    <div className="notice notice--error" role="alert">
      <p className="strong" style={{ marginBottom: onRetry ? 'var(--space-3)' : 0 }}>
        {message}
      </p>
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry} icon="↻">
          {retryLabel}
        </Button>
      ) : null}
    </div>
  )
}

export function EmptyState({
  icon = '🗂️',
  title,
  description,
  action,
}: {
  icon?: string
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="empty-state">
      <span className="empty-state__icon" aria-hidden="true">
        {icon}
      </span>
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
      {action}
    </div>
  )
}

export function Notice({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'warn' | 'error' | 'success'
  title?: string
  children: ReactNode
}) {
  return (
    <div className={`notice ${tone !== 'info' ? `notice--${tone}` : ''}`}>
      {title ? <p className="strong" style={{ marginBottom: 'var(--space-2)' }}>{title}</p> : null}
      {children}
    </div>
  )
}

export function Meter({
  value,
  label,
  tone = 'default',
}: {
  value: number
  label?: string
  tone?: 'default' | 'good' | 'warn'
}) {
  const percent = Math.max(0, Math.min(100, Math.round(value * 100)))
  return (
    <div>
      {label ? (
        <div className="row row--between tiny muted" style={{ marginBottom: 4 }}>
          <span>{label}</span>
          <span>{percent}%</span>
        </div>
      ) : null}
      <div
        className="meter"
        role="meter"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? 'score'}
      >
        <div
          className={`meter__fill ${tone !== 'default' ? `meter__fill--${tone}` : ''}`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  )
}

/** Verification status shown honestly - never dressed up as more than it is. */
export function VerificationChip({ status }: { status: string }) {
  const map: Record<string, { tone: ChipTone; icon: string; label: string }> = {
    admin_verified: { tone: 'good', icon: '✓', label: 'Verified by staff' },
    certification_verified: { tone: 'good', icon: '🎓', label: 'Certified' },
    assessment_verified: { tone: 'good', icon: '📋', label: 'Assessed' },
    training_verified: { tone: 'info', icon: '📘', label: 'Training verified' },
    self_declared: { tone: 'warn', icon: '🗣️', label: 'You told us' },
    unverified: { tone: 'warn', icon: '•', label: 'Not verified' },
    disputed: { tone: 'bad', icon: '!', label: 'Disputed' },
  }
  const entry = map[status] ?? { tone: 'neutral' as ChipTone, icon: '•', label: status }
  return (
    <Chip tone={entry.tone} icon={entry.icon} title={`Verification status: ${status}`}>
      {entry.label}
    </Chip>
  )
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

export function daysAgo(value: string | null | undefined): string {
  if (!value) return 'never'
  const days = Math.round((Date.now() - new Date(value).getTime()) / 86_400_000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days} days ago`
  if (days < 365) return `${Math.round(days / 30)} months ago`
  return `${Math.round(days / 365)} years ago`
}
