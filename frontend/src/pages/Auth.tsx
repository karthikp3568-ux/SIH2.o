import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { api, storeSession } from '../api/client'
import { Icon } from '../components/Icon'
import { Layout } from '../components/Layout'
import { Button, Card, ErrorState, Notice } from '../components/ui'
import { useAction } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'

export function SignIn() {
  const { signIn, t } = useApp()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = params.get('next') ?? '/'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const submit = useAction(async () => {
    const user = await signIn(email, password)
    navigate(user.role === 'admin' || user.role === 'counsellor' ? '/admin' : next)
    return user
  })

  return (
    <Layout>
      <div style={{ maxWidth: 460, margin: '0 auto' }} className="stack">
        <h1>{t('nav.signIn')}</h1>
        <Card>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void submit.run()
            }}
          >
            <div className="field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>
            {submit.error ? (
              <div style={{ marginTop: 'var(--space-4)' }}>
                <ErrorState message={submit.error} />
              </div>
            ) : null}
            <div style={{ marginTop: 'var(--space-5)' }}>
              <Button type="submit" block size="lg" loading={submit.pending}>
                {t('nav.signIn')}
              </Button>
            </div>
          </form>
        </Card>

        <p className="center small">
          New here? <Link to="/register">Create an account</Link>
        </p>

        <Notice tone="info" title="Demo accounts">
          <p className="small" style={{ margin: 0 }}>
            Beneficiary: <code>ravi@navigator.example.com</code> / <code>Ravi@12345</code>
            <br />
            Administrator: <code>admin@navigator.example.com</code> / <code>Admin@12345</code>
            <br />
            These exist only because <code>DEMO_MODE</code> is on. They are seeded, not real accounts.
          </p>
        </Notice>
      </div>
    </Layout>
  )
}

/** Mirrors the server's rules (backend/app/security.py) so people see them before submitting. */
const PASSWORD_RULES: { label: string; test: (value: string) => boolean }[] = [
  { label: 'At least 8 characters', test: (v) => v.length >= 8 },
  { label: 'An uppercase letter (A–Z)', test: (v) => /[A-Z]/.test(v) },
  { label: 'A lowercase letter (a–z)', test: (v) => /[a-z]/.test(v) },
  { label: 'A number (0–9)', test: (v) => /[0-9]/.test(v) },
]

export function Register() {
  const navigate = useNavigate()
  const { adoptSession, language } = useApp()
  const [form, setForm] = useState({
    email: '',
    full_name: '',
    password: '',
    consent_profile_processing: false,
    consent_voice_processing: false,
    consent_location_processing: false,
    consent_outcome_tracking: false,
  })

  const submit = useAction(async () => {
    const response = await api.register({ ...form, preferred_language: language })
    storeSession(response)
    adoptSession(response)
    navigate('/start')
    return response
  })

  const update = (key: keyof typeof form, value: string | boolean) =>
    setForm((current) => ({ ...current, [key]: value }))

  return (
    <Layout>
      <div style={{ maxWidth: 520, margin: '0 auto' }} className="stack">
        <h1>Create your account</h1>
        <Card>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void submit.run()
            }}
          >
            <div className="field">
              <label htmlFor="name">Your name</label>
              <input
                id="name"
                type="text"
                value={form.full_name}
                onChange={(event) => update('full_name', event.target.value)}
                required
                minLength={2}
              />
            </div>
            <div className="field">
              <label htmlFor="reg-email">Email</label>
              <input
                id="reg-email"
                type="email"
                autoComplete="username"
                value={form.email}
                onChange={(event) => update('email', event.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="reg-password">Password</label>
              <input
                id="reg-password"
                type="password"
                autoComplete="new-password"
                value={form.password}
                onChange={(event) => update('password', event.target.value)}
                required
                minLength={8}
              />
              <ul className="pw-rules" aria-label="Password rules">
                {PASSWORD_RULES.map((rule) => {
                  const met = rule.test(form.password)
                  return (
                    <li key={rule.label} className={met ? 'is-met' : ''}>
                      <Icon name={met ? 'check' : 'circle'} size={13} strokeWidth={met ? 3 : 2} />
                      {rule.label}
                      <span className="visually-hidden">{met ? ' — done' : ' — still needed'}</span>
                    </li>
                  )
                })}
              </ul>
            </div>

            <fieldset style={{ border: 0, padding: 0, margin: 'var(--space-5) 0 0' }}>
              <legend className="strong" style={{ marginBottom: 'var(--space-3)' }}>
                What you agree to
              </legend>

              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.consent_profile_processing}
                  onChange={(event) => update('consent_profile_processing', event.target.checked)}
                  required
                />
                <span>
                  <strong>Required.</strong> Store the details I give about my education, work and
                  skills, so suitable pathways can be found for me.
                </span>
              </label>

              <label className="checkbox" style={{ marginTop: 'var(--space-3)' }}>
                <input
                  type="checkbox"
                  checked={form.consent_voice_processing}
                  onChange={(event) => update('consent_voice_processing', event.target.checked)}
                />
                <span>
                  Process what I say by voice. Recognition happens in my browser; the text is stored,
                  and audio is not kept unless I am told otherwise.
                </span>
              </label>

              <label className="checkbox" style={{ marginTop: 'var(--space-3)' }}>
                <input
                  type="checkbox"
                  checked={form.consent_location_processing}
                  onChange={(event) => update('consent_location_processing', event.target.checked)}
                />
                <span>Use my location to measure distance to opportunities.</span>
              </label>

              <label className="checkbox" style={{ marginTop: 'var(--space-3)' }}>
                <input
                  type="checkbox"
                  checked={form.consent_outcome_tracking}
                  onChange={(event) => update('consent_outcome_tracking', event.target.checked)}
                />
                <span>Track what happens after I choose a pathway, to improve future matching.</span>
              </label>
            </fieldset>

            {submit.error ? (
              <div style={{ marginTop: 'var(--space-4)' }}>
                <ErrorState message={submit.error} />
              </div>
            ) : null}

            <div style={{ marginTop: 'var(--space-5)' }}>
              <Button type="submit" block size="lg" loading={submit.pending}>
                Create account
              </Button>
            </div>
          </form>
        </Card>
        <p className="center small">
          Already have an account? <Link to="/signin">Sign in</Link>
        </p>
      </div>
    </Layout>
  )
}
