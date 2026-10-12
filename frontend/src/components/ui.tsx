/**
 * Shared UI primitives.
 *
 * Every status indicator pairs an icon and a word with its colour, so meaning
 * never depends on colour perception alone.
 */

import { useEffect, useRef } from 'react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { Icon } from './Icon'
import type { IconName } from './Icon'

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
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'dark' | 'success'
  size?: 'sm' | 'md' | 'lg'
  block?: boolean
  loading?: boolean
  icon?: IconName | string
  iconRight?: IconName | string
}

export function Button({
  variant = 'primary',
  size = 'md',
  block = false,
  loading = false,
  icon,
  iconRight,
  children,
  className = '',
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  const classes = [
    'btn',
    variant !== 'primary' ? `btn--${variant}` : '',
    size !== 'md' ? `btn--${size}` : '',
    block ? 'btn--block' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')
  const iconSize = size === 'lg' ? 22 : size === 'sm' ? 16 : 18

  return (
    <button className={classes} disabled={disabled || loading} type={type} {...rest}>
      {loading ? <span className="spinner" aria-hidden="true" /> : icon ? <Icon name={icon} size={iconSize} /> : null}
      {children}
      {iconRight && !loading ? <Icon name={iconRight} size={iconSize} /> : null}
    </button>
  )
}

export type ChipTone = 'neutral' | 'good' | 'info' | 'warn' | 'bad' | 'dark'

export function Chip({
  tone = 'neutral',
  icon,
  children,
  title,
  size,
  className = '',
}: {
  tone?: ChipTone
  icon?: IconName | string
  children: ReactNode
  title?: string
  size?: 'lg'
  className?: string
}) {
  return (
    <span
      className={`chip ${tone !== 'neutral' ? `chip--${tone}` : ''} ${size === 'lg' ? 'chip--lg' : ''} ${className}`}
      title={title}
    >
      {icon ? <Icon name={icon} size={size === 'lg' ? 16 : 14} strokeWidth={2.4} /> : null}
      {children}
    </span>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="loading-block" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

/** Human-readable error. Raw server detail is never the only thing shown. */
export function ErrorState({
  message,
  title = 'Something did not work',
  onRetry,
  retryLabel = 'Try again',
  children,
}: {
  message: string
  title?: string
  onRetry?: () => void
  retryLabel?: string
  children?: ReactNode
}) {
  return (
    <div className="notice notice--error" role="alert">
      <span className="notice__icon">
        <Icon name="alert" />
      </span>
      <div className="grow">
        <div className="notice__title">{title}</div>
        <p className="small ink-2">{message}</p>
        {onRetry || children ? (
          <div className="row" style={{ marginTop: 'var(--space-3)' }}>
            {onRetry ? (
              <Button variant="secondary" size="sm" onClick={onRetry} icon="refresh">
                {retryLabel}
              </Button>
            ) : null}
            {children}
          </div>
        ) : null}
      </div>
    </div>
  )
}

export function EmptyState({
  icon = 'compass',
  title,
  description,
  action,
}: {
  icon?: IconName | string
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="empty-state">
      <div className="empty-state__art">
        <Icon name={icon} size={36} strokeWidth={1.6} />
      </div>
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
      {action ? <div className="row">{action}</div> : null}
    </div>
  )
}

const NOTICE_ICON: Record<string, IconName> = {
  info: 'info',
  warn: 'alert',
  error: 'alert',
  success: 'checkCircle',
}

export function Notice({
  tone = 'info',
  title,
  children,
  icon,
}: {
  tone?: 'info' | 'warn' | 'error' | 'success'
  title?: string
  children?: ReactNode
  icon?: IconName | string
}) {
  return (
    <div className={`notice ${tone !== 'info' ? `notice--${tone}` : ''}`}>
      <span className="notice__icon">
        <Icon name={icon ?? NOTICE_ICON[tone]} />
      </span>
      <div className="grow">
        {title ? <div className="notice__title">{title}</div> : null}
        {children}
      </div>
    </div>
  )
}

export function Meter({
  value,
  label,
  tone = 'default',
  showValue = true,
}: {
  value: number
  label?: string
  tone?: 'default' | 'good' | 'warn' | 'navy'
  showValue?: boolean
}) {
  const percent = Math.max(0, Math.min(100, Math.round(value * 100)))
  return (
    <div>
      {label ? (
        <div className="row row--between tiny muted" style={{ marginBottom: 6 }}>
          <span>{label}</span>
          {showValue ? <span className="strong">{percent}%</span> : null}
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

/** How a skill or fact became known — shown honestly, never dressed up. */
export function VerificationChip({ status }: { status: string }) {
  const map: Record<string, { tone: ChipTone; icon: IconName; label: string }> = {
    admin_verified: { tone: 'good', icon: 'shield', label: 'Verified by staff' },
    certification_verified: { tone: 'good', icon: 'cap', label: 'Certified' },
    assessment_verified: { tone: 'good', icon: 'checkCircle', label: 'Assessed' },
    training_verified: { tone: 'info', icon: 'book', label: 'Training verified' },
    self_declared: { tone: 'warn', icon: 'mic', label: 'You told us' },
    unverified: { tone: 'warn', icon: 'circle', label: 'Not yet verified' },
    disputed: { tone: 'bad', icon: 'alert', label: 'Disputed' },
  }
  const entry = map[status] ?? { tone: 'neutral' as ChipTone, icon: 'dot', label: status.replace(/_/g, ' ') }
  return (
    <Chip tone={entry.tone} icon={entry.icon} title={`Verification status: ${status.replace(/_/g, ' ')}`}>
      {entry.label}
    </Chip>
  )
}

// ---------------------------------------------------------------------------
// Data trust
// ---------------------------------------------------------------------------

export type TrustLevel = 'verified' | 'recent' | 'review' | 'expired'

export function daysSince(value: string | null | undefined): number | null {
  if (!value) return null
  const time = new Date(value).getTime()
  if (Number.isNaN(time)) return null
  return Math.max(0, Math.floor((Date.now() - time) / 86_400_000))
}

/**
 * Trust in plain words. Staff-verified within 90 days reads as verified; a
 * record nobody has checked for a quarter reads as needing verification.
 */
export function trustLevel(opts: {
  verificationStatus: string
  lastVerifiedAt: string | null | undefined
  validUntil?: string | null
}): TrustLevel {
  if (opts.validUntil && new Date(opts.validUntil).getTime() < Date.now()) return 'expired'
  if (['unverified', 'disputed'].includes(opts.verificationStatus)) return 'review'
  const age = daysSince(opts.lastVerifiedAt)
  const staffVerified = ['admin_verified', 'certification_verified'].includes(opts.verificationStatus)
  if (age === null || age > 90) return 'review'
  if (staffVerified) return 'verified'
  return 'recent'
}

const TRUST_META: Record<TrustLevel, { icon: IconName; label: string }> = {
  verified: { icon: 'check', label: 'Verified source' },
  recent: { icon: 'clock', label: 'Recently checked' },
  review: { icon: 'alert', label: 'Needs verification' },
  expired: { icon: 'x', label: 'Expired' },
}

export function TrustBadge({
  verificationStatus,
  lastVerifiedAt,
  validUntil,
  compact = false,
}: {
  verificationStatus: string
  lastVerifiedAt: string | null | undefined
  validUntil?: string | null
  compact?: boolean
}) {
  const level = trustLevel({ verificationStatus, lastVerifiedAt, validUntil })
  const meta = TRUST_META[level]
  const when = lastVerifiedAt ? `Updated ${daysAgo(lastVerifiedAt)}` : 'Never checked'
  return (
    <span className={`trust trust--${level}`} title={`${meta.label}. ${when}.`}>
      <span className="trust__icon">
        <Icon name={meta.icon} size={13} strokeWidth={3} />
      </span>
      <span>
        <span className="trust__label">{meta.label}</span>
        {compact ? null : <span className="trust__when" style={{ display: 'block' }}>{when}</span>}
      </span>
    </span>
  )
}

// ---------------------------------------------------------------------------
// Opportunity lifecycle status
// ---------------------------------------------------------------------------

export type OpportunityState = 'active' | 'expiring' | 'stale' | 'unverified' | 'inactive' | 'draft'

export function opportunityState(o: {
  status: string
  verification_status: string
  last_verified_at: string | null
  valid_until: string | null
}): OpportunityState {
  if (o.status === 'draft') return 'draft'
  if (o.status !== 'active') return 'inactive'
  if (o.valid_until && new Date(o.valid_until).getTime() < Date.now()) return 'inactive'
  if (o.verification_status === 'unverified' || !o.last_verified_at) return 'unverified'
  const age = daysSince(o.last_verified_at) ?? 999
  if (age > 90) return 'stale'
  if (o.valid_until) {
    const daysLeft = (new Date(o.valid_until).getTime() - Date.now()) / 86_400_000
    if (daysLeft <= 30) return 'expiring'
  }
  return 'active'
}

const STATE_META: Record<OpportunityState, { icon: IconName; label: string }> = {
  active: { icon: 'check', label: 'Active' },
  expiring: { icon: 'clock', label: 'Expiring' },
  stale: { icon: 'alert', label: 'Stale' },
  unverified: { icon: 'circle', label: 'Unverified' },
  inactive: { icon: 'x', label: 'Inactive' },
  draft: { icon: 'edit', label: 'Draft' },
}

export function StatusChip({ state }: { state: OpportunityState }) {
  const meta = STATE_META[state]
  return (
    <span className={`status-chip status-chip--${state}`}>
      <Icon name={meta.icon} size={12} strokeWidth={3} />
      {meta.label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Overlays
// ---------------------------------------------------------------------------

export function Drawer({
  open,
  onClose,
  title,
  eyebrow,
  children,
  footer,
  labelledBy = 'drawer-title',
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  eyebrow?: ReactNode
  children: ReactNode
  footer?: ReactNode
  labelledBy?: string
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const previousFocus = useRef<Element | null>(null)
  // A ref, so an inline onClose does not re-run the effect and steal focus.
  const close = useRef(onClose)
  close.current = onClose

  useEffect(() => {
    if (!open) return
    previousFocus.current = document.activeElement
    panelRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close.current()
    }
    document.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
      ;(previousFocus.current as HTMLElement | null)?.focus?.()
    }
  }, [open])

  if (!open) return null
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <div
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        ref={panelRef}
        tabIndex={-1}
      >
        <div className="drawer__head">
          <div className="grow">
            {eyebrow ? <div className="eyebrow" style={{ marginBottom: 6 }}>{eyebrow}</div> : null}
            <h2 id={labelledBy} style={{ margin: 0, fontSize: '1.3rem' }}>
              {title}
            </h2>
          </div>
          <Button variant="ghost" className="btn--icon" onClick={onClose} aria-label="Close panel">
            <Icon name="x" />
          </Button>
        </div>
        <div className="drawer__body">{children}</div>
        {footer ? <div className="drawer__foot">{footer}</div> : null}
      </div>
    </>
  )
}

export function Toast({ message, onDone }: { message: string | null; onDone: () => void }) {
  // Held in a ref so an inline callback does not restart the timer on re-render.
  const done = useRef(onDone)
  done.current = onDone
  useEffect(() => {
    if (!message) return
    const timer = window.setTimeout(() => done.current(), 3200)
    return () => window.clearTimeout(timer)
  }, [message])
  if (!message) return null
  return (
    <div className="toast" role="status" aria-live="polite">
      <Icon name="checkCircle" size={18} />
      {message}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

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

export function humanize(value: string | null | undefined): string {
  if (!value) return ''
  const text = String(value).replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function formatInr(value: number | null | undefined): string | null {
  if (value === null || value === undefined) return null
  return `₹${Math.round(value).toLocaleString('en-IN')}`
}
