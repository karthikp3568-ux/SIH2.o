import { Link, NavLink, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'

import { useApp } from '../state/AppContext'
import { Icon } from './Icon'
import type { IconName } from './Icon'

export function BrandMark({ size = 20 }: { size?: number }) {
  // A path that bends toward a destination: the navigator's mark.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="6" cy="18" r="2.4" fill="currentColor" />
      <path
        d="M6 15.5V12a4 4 0 0 1 4-4h5"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path d="M14 4.5 18.5 8 14 11.5" stroke="#16a391" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function Brand({ to = '/' }: { to?: string }) {
  return (
    <Link to={to} className="brand" aria-label="Que Sera Livelihood Navigator, home">
      <span className="brand__mark">
        <BrandMark />
      </span>
      <span className="brand__text">
        <span className="brand__name">QUE SERA</span>
        <span className="brand__sub">Livelihood Navigator</span>
      </span>
    </Link>
  )
}

export function LanguagePicker() {
  const { language, languages, setLanguage } = useApp()
  return (
    <span className="lang-select">
      <Icon name="globe" size={16} />
      <select
        value={language}
        onChange={(event) => setLanguage(event.target.value)}
        aria-label="Choose language"
      >
        {languages.map((option) => (
          <option key={option.code} value={option.code}>
            {option.label}
          </option>
        ))}
      </select>
    </span>
  )
}

const BENEFICIARY_NAV: { to: string; key: string; fallback: string; icon: IconName }[] = [
  { to: '/', key: 'nav.home', fallback: 'Home', icon: 'home' },
  { to: '/profile', key: 'nav.profile', fallback: 'My Profile', icon: 'user' },
  { to: '/skills', key: 'nav.skills', fallback: 'My Skills', icon: 'graph' },
  { to: '/pathways', key: 'nav.pathways', fallback: 'Pathways', icon: 'route' },
  { to: '/journey', key: 'nav.journey', fallback: 'My Journey', icon: 'flag' },
]

export function Layout({
  children,
  bare = false,
}: {
  children: ReactNode
  /** Skip the page container, for screens that manage their own width. */
  bare?: boolean
  wide?: boolean
}) {
  const { t, isAuthenticated, isAdmin, user, signOut } = useApp()
  const navigate = useNavigate()
  const showBeneficiaryNav = isAuthenticated && user?.role === 'beneficiary'

  const handleSignOut = async () => {
    await signOut()
    navigate('/')
  }

  return (
    <div className={`app-shell ${showBeneficiaryNav ? 'app-shell--with-bottomnav' : ''}`}>
      <a className="skip-link" href="#main">
        Skip to main content
      </a>

      <header className="topbar">
        <div className="container topbar__inner">
          <Brand />

          {showBeneficiaryNav ? (
            <nav className="topnav" aria-label="Main">
              {BENEFICIARY_NAV.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.to === '/'}>
                  <Icon name={item.icon} size={17} />
                  {t(item.key)}
                </NavLink>
              ))}
            </nav>
          ) : null}

          <div className="topbar__actions">
            {isAdmin ? (
              <Link to="/admin" className="btn btn--dark btn--sm">
                <Icon name="chart" size={16} />
                {t('nav.admin')}
              </Link>
            ) : null}
            <LanguagePicker />
            {isAuthenticated ? (
              <button
                type="button"
                className="btn btn--ghost btn--icon btn--sm"
                onClick={handleSignOut}
                aria-label={t('nav.signOut')}
                title={t('nav.signOut')}
              >
                <Icon name="logout" size={18} />
              </button>
            ) : (
              <Link to="/signin" className="btn btn--secondary btn--sm">
                {t('nav.signIn')}
              </Link>
            )}
          </div>
        </div>
      </header>

      <main id="main">{bare ? children : <div className="container page">{children}</div>}</main>

      <footer className="site-footer">
        <div className="container">
          <p>
            <strong>Que Sera · Livelihood Navigator</strong> — suggestions only; the decision is always yours.
          </p>
          <p>
            <Link to="/signin?as=admin">Staff console</Link>
          </p>
        </div>
      </footer>

      {showBeneficiaryNav ? (
        <nav className="bottomnav" aria-label="Main">
          {BENEFICIARY_NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === '/'}>
              <Icon name={item.icon} size={22} />
              {t(item.key)}
            </NavLink>
          ))}
        </nav>
      ) : null}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Admin shell
// ---------------------------------------------------------------------------

export const ADMIN_NAV: { to: string; label: string; icon: IconName }[] = [
  { to: '/admin', label: 'Overview', icon: 'chart' },
  { to: '/admin/beneficiaries', label: 'Beneficiaries', icon: 'users' },
  { to: '/admin/opportunities', label: 'Opportunities', icon: 'briefcase' },
  { to: '/admin/recommendations', label: 'Recommendations', icon: 'inbox' },
  { to: '/admin/outcomes', label: 'Outcomes', icon: 'trending' },
  { to: '/admin/verification', label: 'Verification', icon: 'shield' },
  { to: '/admin/audit', label: 'Audit', icon: 'file' },
]

export function AdminLayout({
  title,
  actions,
  children,
  reviewCount,
}: {
  title: string
  actions?: ReactNode
  children: ReactNode
  reviewCount?: number
}) {
  const { user, signOut } = useApp()
  const navigate = useNavigate()

  return (
    <div className="admin-shell">
      <a className="skip-link" href="#admin-main">
        Skip to main content
      </a>
      <aside className="admin-side" aria-label="Administration">
        <Brand to="/admin" />
        <nav className="admin-nav">
          {ADMIN_NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === '/admin'}>
              <Icon name={item.icon} size={18} />
              {item.label}
              {item.to === '/admin/recommendations' && reviewCount ? (
                <span className="admin-nav__count" aria-label={`${reviewCount} awaiting review`}>
                  {reviewCount}
                </span>
              ) : null}
            </NavLink>
          ))}
        </nav>
        <div className="admin-side__foot">
          <strong>{user?.full_name}</strong>
          {user?.role === 'counsellor' ? 'Counsellor' : 'Administrator'} · {user?.email}
          <div>
            <button
              type="button"
              onClick={async () => {
                await signOut()
                navigate('/')
              }}
            >
              <Icon name="logout" size={16} /> Sign out
            </button>
          </div>
          <Link to="/system" className="admin-side__system">
            System status
          </Link>
        </div>
      </aside>

      <div className="admin-main">
        <nav className="admin-mobile-nav" aria-label="Administration">
          {ADMIN_NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === '/admin'}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <header className="admin-head">
          <h1 className="grow">{title}</h1>
          {actions}
        </header>
        <main id="admin-main" className="admin-body">
          {children}
        </main>
      </div>
    </div>
  )
}
