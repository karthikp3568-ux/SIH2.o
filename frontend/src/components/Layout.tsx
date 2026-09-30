import { NavLink, Link, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'

import { useApp } from '../state/AppContext'

function LanguagePicker() {
  const { language, languages, setLanguage } = useApp()
  return (
    <label className="visually-hidden-label" style={{ margin: 0 }}>
      <span className="visually-hidden">Language</span>
      <select
        value={language}
        onChange={(event) => setLanguage(event.target.value)}
        style={{
          minHeight: 40,
          padding: '6px 10px',
          borderRadius: 8,
          border: '1px solid rgba(255,255,255,0.35)',
          background: 'rgba(255,255,255,0.1)',
          color: '#fff',
          fontWeight: 600,
        }}
        aria-label="Choose language"
      >
        {languages.map((option) => (
          <option key={option.code} value={option.code} style={{ color: '#1b2733' }}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

export function Layout({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  const { t, isAuthenticated, isAdmin, user, signOut } = useApp()
  const navigate = useNavigate()

  const handleSignOut = async () => {
    await signOut()
    navigate('/')
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>

      <header className="site-header">
        <div className={`container ${wide ? 'container--wide' : ''} row row--between`}>
          <Link to="/" className="brand">
            <span className="brand__mark" aria-hidden="true">
              ⌂
            </span>
            <span>
              {t('app.name')}
              <span className="brand__sub">{t('app.tagline')}</span>
            </span>
          </Link>

          <nav className="row" aria-label="Main">
            {isAuthenticated && user?.role === 'beneficiary' ? (
              <>
                <NavLink to="/pathways" className="btn btn--ghost" style={{ color: '#fff' }}>
                  {t('nav.pathways')}
                </NavLink>
                <NavLink to="/progress" className="btn btn--ghost" style={{ color: '#fff' }}>
                  {t('nav.progress')}
                </NavLink>
              </>
            ) : null}
            {isAdmin ? (
              <NavLink to="/admin" className="btn btn--ghost" style={{ color: '#fff' }}>
                {t('nav.admin')}
              </NavLink>
            ) : null}
            <LanguagePicker />
            {isAuthenticated ? (
              <button className="btn btn--ghost" style={{ color: '#fff' }} onClick={handleSignOut}>
                {t('nav.signOut')}
              </button>
            ) : (
              <NavLink to="/signin" className="btn btn--secondary">
                {t('nav.signIn')}
              </NavLink>
            )}
          </nav>
        </div>
      </header>

      <main id="main">
        <div className={`container ${wide ? 'container--wide' : ''}`}>{children}</div>
      </main>

      <footer className="site-footer">
        <div className={`container ${wide ? 'container--wide' : ''} stack-sm`}>
          <p style={{ margin: 0 }}>
            {t('app.name')} — a prototype built for Smart India Hackathon 2026 (SIH26097).
          </p>
          <p style={{ margin: 0 }} className="tiny">
            Qualification and opportunity records in this build are demonstration data modelled on
            the NSQF / QP / NOS structure. They are not an authoritative extract, and this prototype
            makes no claim of regulatory compliance. Recommendations are suggestions — the decision
            is always yours.
          </p>
          <p style={{ margin: 0 }} className="tiny">
            <Link to="/system">System and data sources</Link>
          </p>
        </div>
      </footer>
    </div>
  )
}
