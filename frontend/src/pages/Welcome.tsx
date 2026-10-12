/**
 * Landing screen.
 *
 * One primary action — start talking — with typing as an equal second path.
 * Interactive rotating conversational ticker, multi-sector career badges,
 * and dual interactive demo tracks (Rural Tech / Software Engineer).
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import { Icon } from '../components/Icon'
import type { IconName } from '../components/Icon'
import { Layout } from '../components/Layout'
import { Button } from '../components/ui'
import { VoiceOrb } from '../components/voice/VoiceOrb'
import { useAction, useAsync } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'

const FEATURED_LANGUAGES = ['kn', 'hi', 'en', 'ta', 'te', 'mr']

const PROMISES: { icon: IconName; title: string; body: string }[] = [
  {
    icon: 'edit',
    title: 'You check everything',
    body: 'Nothing we understood is saved until you confirm it — and you can change any of it.',
  },
  {
    icon: 'shield',
    title: 'Only checked opportunities',
    body: 'Every listing shows where it came from and when it was last verified.',
  },
  {
    icon: 'info',
    title: 'Every suggestion explained',
    body: 'Each pathway says why it fits you, and what you would still need.',
  },
]

const JOURNEY: { icon: IconName; title: string; body: string }[] = [
  { icon: 'mic', title: 'Voice Intake', body: 'Say what you do or want to do, in your language' },
  { icon: 'user', title: 'Smart Profile', body: 'Check facts and verified skills' },
  { icon: 'graph', title: 'Skill Gap', body: 'See what you have, and what’s next' },
  { icon: 'route', title: 'Pathways', body: 'Verified training, jobs & apprenticeships' },
  { icon: 'sprout', title: 'Livelihood', body: 'Track step-by-step progress & wage growth' },
]

const QUOTES = [
  { text: '“I want to become a software engineer, I know Python and Java…”', field: 'Software & IT' },
  { text: '“I work on my farm and know how to repair irrigation pumps…”', field: 'Agriculture & Machinery' },
  { text: '“I know AutoCAD drafting and want a mechanical engineering job…”', field: 'CAD & Design' },
  { text: '“I do computer hardware troubleshooting and network setup…”', field: 'IT Operations' },
]

const CAREER_TRACKS = [
  { icon: 'code', label: 'Software & Python' },
  { icon: 'wrench', label: 'Machinery & Electrical' },
  { icon: 'sprout', label: 'AgTech & Farming' },
  { icon: 'briefcase', label: 'IT Support & Helpdesk' },
  { icon: 'chart', label: 'CAD & Engineering' },
]

export function Welcome() {
  const { t, isAuthenticated, user, adoptSession, setLanguage, language, languages } = useApp()
  const navigate = useNavigate()
  const status = useAsync(() => api.status(), [])
  const demoMode = status.data?.demo_mode ?? false

  const [quoteIndex, setQuoteIndex] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setQuoteIndex((prev) => (prev + 1) % QUOTES.length)
    }, 3800)
    return () => clearInterval(timer)
  }, [])

  const demo = useAction(async (mode: 'voice' | 'text' | 'guided') => {
    const session = await api.demoReset()
    adoptSession({ user: session.user, tokens: session.tokens })
    const query = mode === 'guided' ? 'demo=1' : `mode=${mode}`
    navigate(`/conversation/${session.conversation_id}?${query}`)
  })

  const start = (mode: 'voice' | 'text') => {
    if (isAuthenticated && user?.role === 'beneficiary') {
      navigate(`/start?mode=${mode}&fresh=1`)
      return
    }
    if (!isAuthenticated && demoMode) {
      void demo.run(mode)
      return
    }
    navigate(`/signin?next=${encodeURIComponent(`/start?mode=${mode}&fresh=1`)}`)
  }

  const featured = FEATURED_LANGUAGES.map((code) => languages.find((l) => l.code === code)).filter(
    (l): l is NonNullable<typeof l> => Boolean(l),
  )
  const others = languages.filter((l) => !FEATURED_LANGUAGES.includes(l.code))

  const currentQuote = QUOTES[quoteIndex]

  return (
    <Layout bare>
      <section className="hero">
        <div className="container hero__inner">
          <div className="hero__copy enter">
            <div className="hero__badge-row">
              <span className="eyebrow">
                <span className="hero__dot" aria-hidden="true" /> Smart India Hackathon · SIH26097
              </span>
              <span className="hero__live-pill">
                <Icon name="sparkle" size={12} /> AI Multilingual Intake
              </span>
            </div>

            <h1 className="hero__title">{t('welcome.hero')}</h1>
            <p className="hero__lead">{t('welcome.subtitle')}</p>

            <div className="hero__actions">
              <Button size="lg" icon="mic" onClick={() => start('voice')} loading={demo.pending}>
                {t('welcome.speak')}
              </Button>
              <Button size="lg" variant="secondary" icon="keyboard" onClick={() => start('text')}>
                {t('welcome.type')}
              </Button>
            </div>

            {demo.error ? (
              <p className="small" role="alert" style={{ color: 'var(--red-600)', marginTop: 12 }}>
                We could not start right now. Please try again in a moment.
              </p>
            ) : null}

            {!isAuthenticated && demoMode ? (
              <p className="tiny muted" style={{ marginTop: 12 }}>
                Quick Demo Mode active: test with ready profiles or speak freely.
              </p>
            ) : null}

            {/* Career track badges */}
            <div className="hero__tracks">
              <span className="hero__tracks-title">Supported Career Sectors:</span>
              <div className="hero__tracks-pills">
                {CAREER_TRACKS.map((track) => (
                  <span key={track.label} className="track-pill">
                    <Icon name={track.icon} size={13} />
                    {track.label}
                  </span>
                ))}
              </div>
            </div>

            {/* Language Selection */}
            <div className="hero__langs" role="group" aria-label={t('welcome.language')}>
              {featured.map((option) => (
                <button
                  key={option.code}
                  type="button"
                  className="lang-pill"
                  aria-pressed={language === option.code}
                  onClick={() => setLanguage(option.code)}
                  lang={option.code}
                >
                  {option.label}
                </button>
              ))}
              {others.length > 0 ? (
                <select
                  className="lang-pill lang-pill--select"
                  aria-label="More languages"
                  value={others.some((o) => o.code === language) ? language : ''}
                  onChange={(event) => event.target.value && setLanguage(event.target.value)}
                >
                  <option value="">More…</option>
                  {others.map((option) => (
                    <option key={option.code} value={option.code}>
                      {option.label}
                    </option>
                  ))}
                </select>
              ) : null}
            </div>
          </div>

          <div className="hero__visual">
            <button
              type="button"
              className="hero__orb-button"
              onClick={() => start('voice')}
              aria-label={t('welcome.speak')}
            >
              <VoiceOrb state="idle" size={320} label="AI Voice assistant, ready to listen" />
              <span className="hero__orb-mic" aria-hidden="true">
                <Icon name="mic" size={28} />
              </span>
            </button>
            <div className="hero__quote-card">
              <span className="hero__quote-tag">{currentQuote.field}</span>
              <p className="hero__quote-text">{currentQuote.text}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="container journey-strip-wrap" aria-labelledby="journey-strip-title">
        <h2 id="journey-strip-title" className="visually-hidden">
          How it works
        </h2>
        <ol className="journey-strip">
          {JOURNEY.map((step) => (
            <li key={step.title} className="journey-strip__step">
              <span className="journey-strip__icon" aria-hidden="true">
                <Icon name={step.icon} size={22} />
              </span>
              <span className="journey-strip__title">{step.title}</span>
              <span className="journey-strip__body">{step.body}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="container landing-lower">
        <div className="demo-grid">
          {/* Demo 1: Ravi (Machinery & Farm) */}
          <div className="demo-card">
            <div className="demo-card__person" aria-hidden="true">
              R
            </div>
            <div className="grow">
              <span className="eyebrow">Guided Profile 1</span>
              <h3 style={{ margin: '4px 0 6px' }}>Ravi · Pump Mechanic</h3>
              <p className="small muted" style={{ margin: 0 }}>
                Machinery repair and farm equipment standard (NSQF Level 3/4) with local workshop listings.
              </p>
            </div>
            <Button variant="dark" icon="play" onClick={() => demo.run('guided')} loading={demo.pending}>
              {t('welcome.demo')}
            </Button>
          </div>

          {/* Demo 2: Tech Career (Python / Java / Web) */}
          <div className="demo-card demo-card--tech">
            <div className="demo-card__person demo-card__person--tech" aria-hidden="true">
              <Icon name="code" size={24} />
            </div>
            <div className="grow">
              <span className="eyebrow" style={{ color: 'var(--teal-700)' }}>Guided Profile 2</span>
              <h3 style={{ margin: '4px 0 6px' }}>Software &amp; Coding Track</h3>
              <p className="small muted" style={{ margin: 0 }}>
                Python, Java &amp; Web development qualification pathways (NSQF Level 5) with IT opportunities.
              </p>
            </div>
            <Button variant="secondary" icon="arrowRight" onClick={() => start('text')}>
              Explore Tech Track
            </Button>
          </div>
        </div>

        <ul className="promises">
          {PROMISES.map((promise) => (
            <li key={promise.title}>
              <span className="icon-tile icon-tile--teal">
                <Icon name={promise.icon} size={20} />
              </span>
              <div>
                <h4 style={{ marginBottom: 4 }}>{promise.title}</h4>
                <p className="small muted" style={{ margin: 0 }}>
                  {promise.body}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </Layout>
  )
}
