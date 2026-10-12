import { useState, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { api, storeSession } from '../api/client'
import { Icon } from '../components/Icon'
import { Layout } from '../components/Layout'
import { Button, Card, ErrorState, Notice } from '../components/ui'
import { useAction } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'

/** Mirrors the server's rules (backend/app/security.py) so people see them before submitting. */
const PASSWORD_RULES: { label: string; test: (value: string) => boolean }[] = [
  { label: 'At least 8 characters', test: (v) => v.length >= 8 },
  { label: 'An uppercase letter (A–Z)', test: (v) => /[A-Z]/.test(v) },
  { label: 'An lowercase letter (a–z)', test: (v) => /[a-z]/.test(v) },
  { label: 'A number (0–9)', test: (v) => /[0-9]/.test(v) },
]

export function SignIn() {
  const { signIn, t } = useApp()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = params.get('next') ?? '/'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  // Forgot Password / Password Reset State
  const [forgotMode, setForgotMode] = useState(false)
  const [resetStep, setResetStep] = useState<'request' | 'confirm'>('request')
  const [resetEmail, setResetEmail] = useState('')
  const [resetCode, setResetCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [resetMessage, setResetMessage] = useState<string | null>(null)
  const [resetDevCode, setResetDevCode] = useState<string | null>(null)
  const [resetCooldown, setResetCooldown] = useState(0)

  useEffect(() => {
    if (resetCooldown <= 0) return
    const timer = setInterval(() => setResetCooldown((prev) => Math.max(0, prev - 1)), 1000)
    return () => clearInterval(timer)
  }, [resetCooldown])

  const submit = useAction(async () => {
    const user = await signIn(email, password)
    navigate(user.role === 'admin' || user.role === 'counsellor' ? '/admin' : next)
    return user
  })

  const requestResetAction = useAction(async () => {
    const res = await api.requestPasswordReset(resetEmail)
    setResetMessage(res.message)
    if (res.dev_code) setResetDevCode(res.dev_code)
    setResetCooldown(res.resend_in_seconds || 60)
    setResetStep('confirm')
  })

  const confirmResetAction = useAction(async () => {
    const res = await api.confirmPasswordReset({
      email: resetEmail,
      code: resetCode,
      new_password: newPassword,
    })
    setResetMessage(res.message)
    setTimeout(() => {
      setForgotMode(false)
      setResetStep('request')
      setEmail(resetEmail)
    }, 1800)
  })

  if (forgotMode) {
    return (
      <Layout>
        <div style={{ maxWidth: 460, margin: '0 auto' }} className="stack">
          <h1>Reset Password</h1>
          <Card>
            {resetStep === 'request' ? (
              <form
                onSubmit={(event) => {
                  event.preventDefault()
                  void requestResetAction.run()
                }}
              >
                <p className="small ink-subtle" style={{ marginTop: 0 }}>
                  Enter your registered email address to receive an expiring verification code.
                </p>
                <div className="field">
                  <label htmlFor="reset-email">Email Address</label>
                  <input
                    id="reset-email"
                    type="email"
                    value={resetEmail}
                    onChange={(e) => setResetEmail(e.target.value)}
                    required
                  />
                </div>
                {requestResetAction.error ? (
                  <div style={{ marginTop: 'var(--space-3)' }}>
                    <ErrorState message={requestResetAction.error} />
                  </div>
                ) : null}
                <div style={{ marginTop: 'var(--space-4)', display: 'flex', gap: 'var(--space-2)' }}>
                  <Button type="submit" loading={requestResetAction.pending}>
                    Send Reset Code
                  </Button>
                  <Button variant="ghost" onClick={() => setForgotMode(false)}>
                    Cancel
                  </Button>
                </div>
              </form>
            ) : (
              <form
                onSubmit={(event) => {
                  event.preventDefault()
                  void confirmResetAction.run()
                }}
              >
                {resetDevCode && (
                  <Notice tone="info" title="Development/Demo Mode">
                    <p className="small" style={{ margin: 0 }}>
                      Active verification code: <strong>{resetDevCode}</strong>
                    </p>
                  </Notice>
                )}
                {resetMessage && (
                  <p className="small" style={{ color: 'var(--teal-700)', fontWeight: 600 }}>
                    {resetMessage}
                  </p>
                )}
                <div className="field">
                  <label htmlFor="reset-code">6-Digit Code</label>
                  <input
                    id="reset-code"
                    type="text"
                    maxLength={6}
                    value={resetCode}
                    onChange={(e) => setResetCode(e.target.value.replace(/\D/g, ''))}
                    placeholder="e.g. 482910"
                    required
                  />
                </div>
                <div className="field">
                  <label htmlFor="reset-new-password">New Password</label>
                  <input
                    id="reset-new-password"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    minLength={8}
                  />
                </div>
                {confirmResetAction.error ? (
                  <div style={{ marginTop: 'var(--space-3)' }}>
                    <ErrorState message={confirmResetAction.error} />
                  </div>
                ) : null}
                <div style={{ marginTop: 'var(--space-4)', display: 'flex', gap: 'var(--space-2)' }}>
                  <Button type="submit" loading={confirmResetAction.pending}>
                    Update Password
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={resetCooldown > 0 || requestResetAction.pending}
                    onClick={() => void requestResetAction.run()}
                  >
                    {resetCooldown > 0 ? `Resend (${resetCooldown}s)` : 'Resend Code'}
                  </Button>
                  <Button variant="ghost" onClick={() => setForgotMode(false)}>
                    Cancel
                  </Button>
                </div>
              </form>
            )}
          </Card>
        </div>
      </Layout>
    )
  }

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
            <div style={{ textAlign: 'right', marginTop: 'var(--space-1)' }}>
              <button
                type="button"
                className="link small"
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                onClick={() => {
                  setForgotMode(true)
                  setResetEmail(email)
                }}
              >
                Forgot password?
              </button>
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

export function Register() {
  const navigate = useNavigate()
  const { adoptSession, language, setLanguage } = useApp()

  // Steps: 'form' -> 'email_otp' -> 'phone_otp' -> 'complete'
  const [step, setStep] = useState<'form' | 'email_otp' | 'phone_otp' | 'complete'>('form')

  const [form, setForm] = useState({
    email: '',
    phone: '',
    full_name: '',
    password: '',
    confirm_password: '',
    consent_profile_processing: false,
    consent_voice_processing: false,
    consent_location_processing: false,
    consent_outcome_tracking: false,
  })

  // OTP State
  const [emailOtp, setEmailOtp] = useState('')
  const [phoneOtp, setPhoneOtp] = useState('')
  const [devEmailOtp, setDevEmailOtp] = useState<string | null>(null)
  const [devPhoneOtp, setDevPhoneOtp] = useState<string | null>(null)
  const [emailCooldown, setEmailCooldown] = useState(0)
  const [phoneCooldown, setPhoneCooldown] = useState(0)
  const [emailVerified, setEmailVerified] = useState(false)
  const [phoneVerified, setPhoneVerified] = useState(false)

  useEffect(() => {
    if (emailCooldown <= 0) return
    const timer = setInterval(() => setEmailCooldown((prev) => Math.max(0, prev - 1)), 1000)
    return () => clearInterval(timer)
  }, [emailCooldown])

  useEffect(() => {
    if (phoneCooldown <= 0) return
    const timer = setInterval(() => setPhoneCooldown((prev) => Math.max(0, prev - 1)), 1000)
    return () => clearInterval(timer)
  }, [phoneCooldown])

  const submit = useAction(async () => {
    if (form.password !== form.confirm_password) {
      throw new Error('Passwords do not match.')
    }
    const response = await api.register({
      email: form.email,
      phone: form.phone || undefined,
      full_name: form.full_name,
      password: form.password,
      preferred_language: language,
      consent_profile_processing: form.consent_profile_processing,
      consent_voice_processing: form.consent_voice_processing,
      consent_location_processing: form.consent_location_processing,
      consent_outcome_tracking: form.consent_outcome_tracking,
    })
    storeSession(response)
    adoptSession(response)

    if (response.dev_otp) {
      setDevEmailOtp(response.dev_otp)
    }
    setEmailCooldown(60)
    setStep('email_otp')
    return response
  })

  const verifyEmailAction = useAction(async () => {
    const res = await api.verifyOtp({
      destination: form.email,
      challenge_type: 'email',
      code: emailOtp,
    })
    setEmailVerified(true)
    if (form.phone && form.phone.trim().length >= 8) {
      // Send phone OTP challenge automatically
      try {
        const phoneRes = await api.sendOtp({
          destination: form.phone,
          challenge_type: 'phone',
        })
        if (phoneRes.dev_code) setDevPhoneOtp(phoneRes.dev_code)
        setPhoneCooldown(60)
      } catch {
        /* proceed to let user manually request */
      }
      setStep('phone_otp')
    } else {
      setStep('complete')
    }
    return res
  })

  const resendEmailOtpAction = useAction(async () => {
    const res = await api.sendOtp({
      destination: form.email,
      challenge_type: 'email',
    })
    if (res.dev_code) setDevEmailOtp(res.dev_code)
    setEmailCooldown(res.resend_in_seconds || 60)
  })

  const sendPhoneOtpAction = useAction(async () => {
    const res = await api.sendOtp({
      destination: form.phone,
      challenge_type: 'phone',
    })
    if (res.dev_code) setDevPhoneOtp(res.dev_code)
    setPhoneCooldown(res.resend_in_seconds || 60)
  })

  const verifyPhoneAction = useAction(async () => {
    const res = await api.verifyOtp({
      destination: form.phone,
      challenge_type: 'phone',
      code: phoneOtp,
    })
    setPhoneVerified(true)
    setStep('complete')
    return res
  })

  const update = (key: keyof typeof form, value: string | boolean) =>
    setForm((current) => ({ ...current, [key]: value }))

  return (
    <Layout>
      <div style={{ maxWidth: 520, margin: '0 auto' }} className="stack">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h1>Create your account</h1>
          <span className="small ink-subtle">
            {step === 'form' && 'Step 1 of 3'}
            {step === 'email_otp' && 'Step 2 of 3'}
            {step === 'phone_otp' && 'Step 3 of 3'}
            {step === 'complete' && 'Verified'}
          </span>
        </div>

        {step === 'form' && (
          <Card>
            <form
              onSubmit={(event) => {
                event.preventDefault()
                void submit.run()
              }}
            >
              <div className="field">
                <label htmlFor="name">Full Name</label>
                <input
                  id="name"
                  type="text"
                  value={form.full_name}
                  onChange={(event) => update('full_name', event.target.value)}
                  placeholder="e.g. Ramesh Kumar"
                  required
                  minLength={2}
                />
              </div>

              <div className="field">
                <label htmlFor="reg-email">Email Address</label>
                <input
                  id="reg-email"
                  type="email"
                  autoComplete="username"
                  value={form.email}
                  onChange={(event) => update('email', event.target.value)}
                  placeholder="ramesh@example.com"
                  required
                />
              </div>

              <div className="field">
                <label htmlFor="reg-phone">Mobile Phone (SMS verification)</label>
                <input
                  id="reg-phone"
                  type="tel"
                  autoComplete="tel"
                  value={form.phone}
                  onChange={(event) => update('phone', event.target.value)}
                  placeholder="+91 98765 43210"
                />
              </div>

              <div className="field">
                <label htmlFor="reg-lang">Preferred Language</label>
                <select
                  id="reg-lang"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value as any)}
                  style={{ padding: '8px 12px', borderRadius: 'var(--radius)', border: '1px solid var(--line-strong)' }}
                >
                  <option value="en">English (Indian English)</option>
                  <option value="hi">हिन्दी (Hindi)</option>
                  <option value="kn">ಕನ್ನಡ (Kannada)</option>
                  <option value="mr">मराठी (Marathi)</option>
                  <option value="ta">தமிழ் (Tamil)</option>
                  <option value="te">తెలుగు (Telugu)</option>
                </select>
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
                      </li>
                    )
                  })}
                </ul>
              </div>

              <div className="field">
                <label htmlFor="reg-confirm-password">Confirm Password</label>
                <input
                  id="reg-confirm-password"
                  type="password"
                  autoComplete="new-password"
                  value={form.confirm_password}
                  onChange={(event) => update('confirm_password', event.target.value)}
                  required
                  minLength={8}
                />
                {form.confirm_password && form.password !== form.confirm_password && (
                  <span className="tiny" style={{ color: 'var(--rose-700)' }}>
                    Passwords do not match.
                  </span>
                )}
              </div>

              <fieldset style={{ border: 0, padding: 0, margin: 'var(--space-4) 0 0' }}>
                <legend className="strong" style={{ marginBottom: 'var(--space-2)' }}>
                  Consent & Terms
                </legend>

                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={form.consent_profile_processing}
                    onChange={(event) => update('consent_profile_processing', event.target.checked)}
                    required
                  />
                  <span>
                    <strong>Required.</strong> Store details about education, skills and preferences for pathway recommendations.
                  </span>
                </label>

                <label className="checkbox" style={{ marginTop: 'var(--space-2)' }}>
                  <input
                    type="checkbox"
                    checked={form.consent_voice_processing}
                    onChange={(event) => update('consent_voice_processing', event.target.checked)}
                  />
                  <span>Process speech audio for multilingual voice assistant turn-taking.</span>
                </label>

                <label className="checkbox" style={{ marginTop: 'var(--space-2)' }}>
                  <input
                    type="checkbox"
                    checked={form.consent_location_processing}
                    onChange={(event) => update('consent_location_processing', event.target.checked)}
                  />
                  <span>Use district/block location to calculate mobility proximity.</span>
                </label>

                <label className="checkbox" style={{ marginTop: 'var(--space-2)' }}>
                  <input
                    type="checkbox"
                    checked={form.consent_outcome_tracking}
                    onChange={(event) => update('consent_outcome_tracking', event.target.checked)}
                  />
                  <span>Track pathway progression (enrolled, completed, employed).</span>
                </label>
              </fieldset>

              {submit.error ? (
                <div style={{ marginTop: 'var(--space-4)' }}>
                  <ErrorState message={submit.error} />
                </div>
              ) : null}

              <div style={{ marginTop: 'var(--space-5)' }}>
                <Button type="submit" block size="lg" loading={submit.pending}>
                  Create Account & Continue
                </Button>
              </div>
            </form>
          </Card>
        )}

        {step === 'email_otp' && (
          <Card>
            <div className="stack">
              <h2>Verify Email Address</h2>
              <p className="small ink-subtle" style={{ margin: 0 }}>
                We sent a 6-digit verification code to <strong>{form.email}</strong>.
              </p>

              {devEmailOtp && (
                <Notice tone="info" title="Development/Demo Mode">
                  <p className="small" style={{ margin: 0 }}>
                    Active verification code: <strong>{devEmailOtp}</strong>
                  </p>
                </Notice>
              )}

              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  void verifyEmailAction.run()
                }}
              >
                <div className="field">
                  <label htmlFor="email-otp-input">Enter 6-Digit Code</label>
                  <input
                    id="email-otp-input"
                    type="text"
                    maxLength={6}
                    value={emailOtp}
                    onChange={(e) => setEmailOtp(e.target.value.replace(/\D/g, ''))}
                    placeholder="e.g. 123456"
                    required
                    style={{ fontSize: '1.4rem', letterSpacing: '4px', textAlign: 'center' }}
                  />
                </div>

                {verifyEmailAction.error && (
                  <div style={{ marginTop: 'var(--space-3)' }}>
                    <ErrorState message={verifyEmailAction.error} />
                  </div>
                )}

                <div style={{ marginTop: 'var(--space-4)', display: 'flex', gap: 'var(--space-2)' }}>
                  <Button type="submit" size="lg" loading={verifyEmailAction.pending}>
                    Verify Email
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={emailCooldown > 0 || resendEmailOtpAction.pending}
                    onClick={() => void resendEmailOtpAction.run()}
                  >
                    {emailCooldown > 0 ? `Resend (${emailCooldown}s)` : 'Resend Code'}
                  </Button>
                </div>
              </form>
            </div>
          </Card>
        )}

        {step === 'phone_otp' && (
          <Card>
            <div className="stack">
              <h2>Verify Mobile Number</h2>
              <p className="small ink-subtle" style={{ margin: 0 }}>
                Enter the SMS verification code sent to <strong>{form.phone}</strong>.
              </p>

              {devPhoneOtp && (
                <Notice tone="info" title="Development/Demo Mode">
                  <p className="small" style={{ margin: 0 }}>
                    Active SMS code: <strong>{devPhoneOtp}</strong>
                  </p>
                </Notice>
              )}

              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  void verifyPhoneAction.run()
                }}
              >
                <div className="field">
                  <label htmlFor="phone-otp-input">Enter 6-Digit SMS Code</label>
                  <input
                    id="phone-otp-input"
                    type="text"
                    maxLength={6}
                    value={phoneOtp}
                    onChange={(e) => setPhoneOtp(e.target.value.replace(/\D/g, ''))}
                    placeholder="e.g. 654321"
                    required
                    style={{ fontSize: '1.4rem', letterSpacing: '4px', textAlign: 'center' }}
                  />
                </div>

                {verifyPhoneAction.error && (
                  <div style={{ marginTop: 'var(--space-3)' }}>
                    <ErrorState message={verifyPhoneAction.error} />
                  </div>
                )}

                <div style={{ marginTop: 'var(--space-4)', display: 'flex', gap: 'var(--space-2)' }}>
                  <Button type="submit" size="lg" loading={verifyPhoneAction.pending}>
                    Verify Phone
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={phoneCooldown > 0 || sendPhoneOtpAction.pending}
                    onClick={() => void sendPhoneOtpAction.run()}
                  >
                    {phoneCooldown > 0 ? `Resend (${phoneCooldown}s)` : 'Resend Code'}
                  </Button>
                  <Button variant="ghost" onClick={() => setStep('complete')}>
                    Skip for now
                  </Button>
                </div>
              </form>
            </div>
          </Card>
        )}

        {step === 'complete' && (
          <Card>
            <div className="stack center" style={{ padding: 'var(--space-4) 0' }}>
              <div
                style={{
                  width: 56,
                  height: 56,
                  borderRadius: '50%',
                  background: 'var(--teal-100)',
                  color: 'var(--teal-700)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto',
                }}
              >
                <Icon name="check" size={28} strokeWidth={3} />
              </div>
              <h2>Account Verified!</h2>
              <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', margin: '4px 0 12px' }}>
                <span className="tiny" style={{ padding: '4px 10px', borderRadius: '12px', background: emailVerified ? 'var(--teal-100)' : 'var(--navy-100)', color: emailVerified ? 'var(--teal-700)' : 'var(--ink-3)', fontWeight: 650 }}>
                  Email: {emailVerified ? 'Verified ✓' : 'Recorded'}
                </span>
                <span className="tiny" style={{ padding: '4px 10px', borderRadius: '12px', background: phoneVerified ? 'var(--teal-100)' : 'var(--navy-100)', color: phoneVerified ? 'var(--teal-700)' : 'var(--ink-3)', fontWeight: 650 }}>
                  Phone: {phoneVerified ? 'Verified ✓' : 'Saved'}
                </span>
              </div>
              <p className="ink-subtle">
                Welcome to Smart Livelihood Navigator, <strong>{form.full_name}</strong>. Your account is ready.
              </p>
              <div style={{ marginTop: 'var(--space-3)' }}>
                <Button size="lg" onClick={() => navigate('/start')}>
                  Start Your Journey
                </Button>
              </div>
            </div>
          </Card>
        )}

        <p className="center small">
          Already have an account? <Link to="/signin">Sign in</Link>
        </p>
      </div>
    </Layout>
  )
}
