/**
 * Landing screen — Smart Livelihood Navigator (SIH26097).
 *
 * Implements Section 15 of the Master Build Specification:
 * 1. Hero with primary action (Start Journey, Type, Sign In, Create Account)
 * 2. How the system works (4-Phase Architecture)
 * 3. What information is considered (8 Factor Nodes)
 * 4. How recommendations are decided (Visual Formula)
 * 5. Our 8 recommendation rules
 * 6. Where the knowledge comes from (NSQF, NAPS, PMKVY, Schemes)
 * 7. What we don't do vs what we do
 * 8. Demonstration scenarios (Software Developer, Data Analyst, Ravi)
 */

import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import { Icon } from '../components/Icon'
import type { IconName } from '../components/Icon'
import { Layout } from '../components/Layout'
import { Button } from '../components/ui'
import { VoiceOrb } from '../components/voice/VoiceOrb'
import { useAction, useAsync } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'

const FEATURED_LANGUAGES = ['kn', 'hi', 'en', 'ta', 'te', 'mr']

const QUOTES = [
  { text: '“I know Python and SQL and want to become a software engineer.”', field: 'Software Developer (IT)' },
  { text: '“I know Excel, but I want to become a data analyst. Do I need Power BI?”', field: 'Data Analyst (BI Tools)' },
  { text: '“I work in agriculture and repair pumps. I want to earn more without traveling far.”', field: 'Ravi (Agritech & Pump Mechanic)' },
  { text: '“I know AutoCAD drafting and want an infrastructure CAD job.”', field: 'CAD Draughtsman (Engineering)' },
]

const FACTORS: { icon: IconName; title: string; desc: string }[] = [
  { icon: 'cap', title: 'Education Tier', desc: 'School level, ITI trade certificate, polytechnic diploma, or graduate degree.' },
  { icon: 'wrench', title: 'Skills & Tools', desc: 'Concrete tools (Excel, Python, CAD) separate from competencies (Data Analysis, Programming).' },
  { icon: 'briefcase', title: 'Work Experience', desc: 'Practical hands-on background in farming, workshop repair, coding, or offices.' },
  { icon: 'target', title: 'Aspirations & Goals', desc: 'Wage employment, formal apprenticeship, or village micro-enterprise.' },
  { icon: 'pin', title: 'District Location', desc: 'Village, block, and district to evaluate commute feasibility.' },
  { icon: 'bus', title: 'Travel Mobility', desc: 'Explicit travel willingness: local block only, taluka, or ready to relocate.' },
  { icon: 'shield', title: 'Scheme Eligibility', desc: 'Age, community/caste criteria, qualification floors, and financial norms.' },
  { icon: 'clock', title: 'Opportunity Availability', desc: 'Seats available, active status, valid-until dates, and trusted provider origins.' },
]

const RULES = [
  { num: 1, title: 'No Expired Listings', desc: 'Expired or inactive opportunities are never presented as open.' },
  { num: 2, title: 'Self-Reported ≠ Certified', desc: 'Self-reported skills are labeled declared until validated by assessment or certificate.' },
  { num: 3, title: 'Eligibility First', desc: 'Eligibility is checked before any opportunity is recommended as a viable pathway.' },
  { num: 4, title: 'Mobility Alters Ranking', desc: 'A closer opportunity with moderate fit outranks a far opportunity for low-mobility users.' },
  { num: 5, title: 'Every Pathway Explained', desc: 'Every recommendation shows “Why this pathway?” with exact matching factors and missing skills.' },
  { num: 6, title: 'No Hallucinated Data', desc: 'If reliable evidence is missing, the system admits it and suggests prerequisite training.' },
  { num: 7, title: 'Beneficiary Confirmation', desc: 'Extracted details must be confirmed and can be edited anytime by the beneficiary.' },
  { num: 8, title: 'You Are The Decision-Maker', desc: 'AI provides decision support; the person always chooses their own future.' },
]

const KNOWLEDGE_SOURCES = [
  { title: 'NSQF & QP-NOS', org: 'National Council for Vocational Education (NCVET)', desc: 'Occupational standards, competency definitions, and qualification levels.' },
  { title: 'Skill India Digital & PMKVY', org: 'Ministry of Skill Development & Entrepreneurship', desc: 'Government-subsidised training centers, free courses, and tool kit grants.' },
  { title: 'National Apprenticeship (NAPS)', org: 'Apprenticeship Training Scheme', desc: 'On-the-job training stipends, industry partnerships, and dual certification.' },
  { title: 'National Career Service (NCS)', org: 'Ministry of Labour & Employment', desc: 'Verified local job openings and district-level employer listings.' },
  { title: 'Welfare & Livelihood Schemes', org: 'PM-AJAY, PM Vishwakarma, PMEGP, Mudra', desc: 'Eligibility-aware matching for SC beneficiaries, artisans, and micro-enterprises.' },
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
    }, 4000)
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
      {/* Top Banner Navigation */}
      <div style={{ background: '#0f172a', color: '#e2e8f0', padding: '8px 16px', fontSize: '0.85rem' }}>
        <div className="container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>
            <strong style={{ color: '#38bdf8' }}>Smart India Hackathon 2026</strong> · Team Que Sera · Problem Statement: <strong>SIH26097</strong>
          </span>
          <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
            <Link to="/system" style={{ color: '#94a3b8', textDecoration: 'none' }}>System Info</Link>
            {isAuthenticated ? (
              <Link to="/profile" style={{ color: '#38bdf8', textDecoration: 'none' }}>My Profile ({user?.full_name})</Link>
            ) : (
              <>
                <Link to="/signin" style={{ color: '#e2e8f0', textDecoration: 'none' }}>Sign In</Link>
                <Link to="/register" style={{ color: '#38bdf8', textDecoration: 'none', fontWeight: 700 }}>Create Account</Link>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Hero Section */}
      <section className="hero">
        <div className="container hero__inner">
          <div className="hero__copy enter">
            <div className="hero__badge-row">
              <span className="eyebrow">
                <span className="hero__dot" aria-hidden="true" /> AI Multilingual Career Advisor
              </span>
              <span className="hero__live-pill">
                <Icon name="sparkle" size={12} /> Voice-First Intake
              </span>
            </div>

            <h1 className="hero__title">Find Your Path to Livelihood.</h1>
            <p className="hero__lead">
              Tell us what you do, what you want to do, and where you want to work. We’ll help you discover a recognized training, job, or self-employment pathway that fits.
            </p>

            <div className="hero__actions">
              <Button size="lg" icon="mic" onClick={() => start('voice')} loading={demo.pending}>
                Start Your Journey
              </Button>
              <Button size="lg" variant="secondary" icon="keyboard" onClick={() => start('text')}>
                Type Instead
              </Button>
              {!isAuthenticated && (
                <>
                  <Button size="lg" variant="ghost" onClick={() => navigate('/signin')}>
                    Sign In
                  </Button>
                  <Button size="lg" variant="ghost" onClick={() => navigate('/register')}>
                    Create Account
                  </Button>
                </>
              )}
            </div>

            {demo.error ? (
              <p className="small" role="alert" style={{ color: 'var(--red-600)', marginTop: 12 }}>
                We could not start right now. Please try again in a moment.
              </p>
            ) : null}

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

      {/* Section 1: How the System Works (4-Phase Architecture) */}
      <section className="home-section home-section--alt">
        <div className="container">
          <div className="home-section__header">
            <span className="eyebrow">Four-Phase Architecture</span>
            <h2>How the System Works</h2>
            <p>From spoken conversational intake to explainable livelihood outcomes.</p>
          </div>
          <div className="factors-grid">
            <div className="factor-card">
              <div className="factor-card__icon"><Icon name="mic" size={22} /></div>
              <h3>1. Understand</h3>
              <p>Multilingual ASR (Kannada, Hindi, English), configurable silence buffer, editable transcripts, and semantic entity extraction.</p>
            </div>
            <div className="factor-card">
              <div className="factor-card__icon"><Icon name="user" size={22} /></div>
              <h3>2. Profile & Reason</h3>
              <p>Constructs structured candidate profile, maps concrete tools vs competencies, and performs rigorous skill-gap diagnostic.</p>
            </div>
            <div className="factor-card">
              <div className="factor-card__icon"><Icon name="route" size={22} /></div>
              <h3>3. Match & Personalize</h3>
              <p>Retrieves NSQF/QP-NOS standards, checks welfare scheme eligibility, measures travel mobility, and ranks top 3 pathways.</p>
            </div>
            <div className="factor-card">
              <div className="factor-card__icon"><Icon name="flag" size={22} /></div>
              <h3>4. Measure & Learn</h3>
              <p>Follows candidate through enrollment, training completion, employment or micro-enterprise, and feedback tracking.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Section 2: What We Look At */}
      <section className="home-section">
        <div className="container">
          <div className="home-section__header">
            <span className="eyebrow">Data Intelligence</span>
            <h2>What We Look At</h2>
            <p>Eight connected diagnostic dimensions evaluated to ensure realistic, accessible opportunities.</p>
          </div>
          <div className="factors-grid">
            {FACTORS.map((f) => (
              <div key={f.title} className="factor-card">
                <div className="factor-card__icon"><Icon name={f.icon} size={20} /></div>
                <h3>{f.title}</h3>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Section 3: How Recommendations Work (The Formula) */}
      <section className="home-section home-section--alt">
        <div className="container">
          <div className="formula-banner">
            <span className="eyebrow" style={{ color: '#38bdf8' }}>Transparent Matching Logic</span>
            <h2 style={{ margin: 0, fontSize: '1.9rem', color: '#fff' }}>How Recommendations Are Decided</h2>
            <div className="formula-banner__row">
              <span className="formula-chip"><Icon name="user" size={16} /> YOUR PROFILE</span>
              <span className="formula-op">+</span>
              <span className="formula-chip"><Icon name="cap" size={16} /> PATHWAY REQUIREMENTS</span>
              <span className="formula-op">+</span>
              <span className="formula-chip"><Icon name="pin" size={16} /> REAL CONSTRAINTS</span>
              <span className="formula-op">=</span>
              <span className="formula-chip formula-chip--result"><Icon name="route" size={16} /> RELEVANT PATHWAYS</span>
            </div>
            <p style={{ maxWidth: 640, margin: '8px 0 0', color: '#cbd5e1', fontSize: '0.98rem' }}>
              We evaluate skill overlap, qualification floor, travel distance, and active availability. No arbitrary percentages or black-box guessing.
            </p>
          </div>
        </div>
      </section>

      {/* Section 4: Our 8 Recommendation Rules */}
      <section className="home-section">
        <div className="container">
          <div className="home-section__header">
            <span className="eyebrow">Ethical Public Service AI</span>
            <h2>Our Recommendation Rules</h2>
            <p>Built into the backend recommendation service to protect beneficiaries from misleading advice.</p>
          </div>
          <div className="rules-grid">
            {RULES.map((r) => (
              <div key={r.num} className="rule-item">
                <div className="rule-num">{r.num}</div>
                <div>
                  <h4>{r.title}</h4>
                  <p>{r.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Section 5: Demonstration Scenarios */}
      <section className="home-section home-section--alt">
        <div className="container">
          <div className="home-section__header">
            <span className="eyebrow">Interactive Demonstration</span>
            <h2>Explore Verified Career Tracks</h2>
            <p>See how the matching engine distinguishes tools from competencies across diverse domains.</p>
          </div>
          <div className="factors-grid">
            {/* Scenario A: Software Developer */}
            <div className="factor-card" style={{ borderTop: '4px solid #3b82f6' }}>
              <span className="eyebrow" style={{ color: '#2563eb' }}>Scenario A · IT &amp; Tech</span>
              <h3 style={{ margin: '6px 0 4px' }}>Software Developer</h3>
              <p style={{ marginBottom: 14 }}>
                Candidate knows Python and SQL. Matches NSQF Level 5 Junior Developer with missing API unit testing.
              </p>
              <Button size="sm" variant="secondary" icon="arrowRight" onClick={() => start('text')}>
                Try Software Track
              </Button>
            </div>

            {/* Scenario B: Data Analyst */}
            <div className="factor-card" style={{ borderTop: '4px solid #8b5cf6' }}>
              <span className="eyebrow" style={{ color: '#7c3aed' }}>Scenario B · Business Intelligence</span>
              <h3 style={{ margin: '6px 0 4px' }}>Data Analyst</h3>
              <p style={{ marginBottom: 14 }}>
                Treats Excel as a spreadsheet tool and identifies required competencies (Data Analysis &amp; Power BI).
              </p>
              <Button size="sm" variant="secondary" icon="arrowRight" onClick={() => start('text')}>
                Try Data Track
              </Button>
            </div>

            {/* Scenario C: Ravi */}
            <div className="factor-card" style={{ borderTop: '4px solid #0d9488' }}>
              <span className="eyebrow" style={{ color: '#0d9488' }}>Scenario C · Agritech &amp; Trades</span>
              <h3 style={{ margin: '6px 0 4px' }}>Ravi · Pump Mechanic</h3>
              <p style={{ marginBottom: 14 }}>
                Farmer with pump repair experience and low mobility. Ranks local micro-enterprise and village service center.
              </p>
              <Button size="sm" variant="dark" icon="play" onClick={() => demo.run('guided')} loading={demo.pending}>
                Launch Ravi Demo
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* Section 6: Where Knowledge Comes From */}
      <section className="home-section">
        <div className="container">
          <div className="home-section__header">
            <span className="eyebrow">Grounding &amp; Provenance</span>
            <h2>Where the Knowledge Comes From</h2>
            <p>Grounded in recognized Indian skilling frameworks and authentic government portal records.</p>
          </div>
          <div className="factors-grid">
            {KNOWLEDGE_SOURCES.map((s) => (
              <div key={s.title} className="factor-card">
                <span className="eyebrow" style={{ color: 'var(--teal-700)' }}>{s.org}</span>
                <h3 style={{ margin: '6px 0 4px' }}>{s.title}</h3>
                <p>{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Section 7: What We Don't Do vs What We Do */}
      <section className="home-section home-section--alt">
        <div className="container">
          <div className="home-section__header">
            <span className="eyebrow">Transparency Guarantee</span>
            <h2>Our Commitments</h2>
            <p>Clear principles on what the platform promises and what it will never claim.</p>
          </div>
          <div className="trust-split">
            <div className="trust-col trust-col--dont">
              <h3><Icon name="x" size={20} strokeWidth={3} /> What We Do NOT Do</h3>
              <ul className="trust-list">
                <li><Icon name="x" size={16} strokeWidth={2.5} /> We never invent jobs or course vacancies.</li>
                <li><Icon name="x" size={16} strokeWidth={2.5} /> We never treat self-reported skills as certified qualifications.</li>
                <li><Icon name="x" size={16} strokeWidth={2.5} /> We never guarantee government scheme grants or employment.</li>
                <li><Icon name="x" size={16} strokeWidth={2.5} /> We never make irrevocable career decisions for the beneficiary.</li>
                <li><Icon name="x" size={16} strokeWidth={2.5} /> We never hide the reasoning behind any recommendation.</li>
              </ul>
            </div>

            <div className="trust-col trust-col--do">
              <h3><Icon name="check" size={20} strokeWidth={3} /> What We DO</h3>
              <ul className="trust-list">
                <li><Icon name="check" size={16} strokeWidth={2.5} /> We explain the exact factors behind every pathway recommendation.</li>
                <li><Icon name="check" size={16} strokeWidth={2.5} /> We allow beneficiaries to inspect, edit, and confirm their profiles.</li>
                <li><Icon name="check" size={16} strokeWidth={2.5} /> We show source provenance, verification status, and freshness dates.</li>
                <li><Icon name="check" size={16} strokeWidth={2.5} /> We offer prerequisite training pathways when direct jobs are unavailable.</li>
                <li><Icon name="check" size={16} strokeWidth={2.5} /> We keep beneficiaries in full control of their livelihood journey.</li>
              </ul>
            </div>
          </div>
        </div>
      </section>
    </Layout>
  )
}
