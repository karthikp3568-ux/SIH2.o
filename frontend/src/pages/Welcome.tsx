import { useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import { Layout } from '../components/Layout'
import { Button, Card, Notice } from '../components/ui'
import { useAction, useAsync } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'

export function Welcome() {
  const { t, isAuthenticated, user, adoptSession, setLanguage, language, languages } = useApp()
  const navigate = useNavigate()
  const { data: status } = useAsync(() => api.status(), [])

  const demo = useAction(async () => {
    const session = await api.demoReset()
    adoptSession({ user: session.user, tokens: session.tokens })
    navigate(`/conversation/${session.conversation_id}?demo=1`)
  })

  const startOwn = (mode: 'voice' | 'text') => {
    if (!isAuthenticated) {
      navigate(`/signin?next=/start&mode=${mode}`)
      return
    }
    navigate(`/start?mode=${mode}`)
  }

  return (
    <Layout>
      <div className="stack-lg">
        <section className="center stack" style={{ paddingTop: 'var(--space-5)' }}>
          <h1 style={{ fontSize: '2.2rem' }}>{t('welcome.title')}</h1>
          <p style={{ fontSize: '1.1rem', maxWidth: 640, margin: '0 auto' }} className="muted">
            {t('welcome.subtitle')}
          </p>
        </section>

        <section aria-labelledby="lang-heading" className="card">
          <h3 id="lang-heading" style={{ marginBottom: 'var(--space-3)' }}>
            {t('welcome.language')}
          </h3>
          <div className="choice-grid grid--4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
            {languages.map((option) => (
              <button
                key={option.code}
                type="button"
                className="choice"
                aria-pressed={language === option.code}
                onClick={() => setLanguage(option.code)}
              >
                <span className="choice__icon" aria-hidden="true">
                  🗣
                </span>
                <span>{option.label}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="grid grid--2">
          <Button size="lg" icon="🎙" onClick={() => startOwn('voice')} block>
            {t('welcome.speak')}
          </Button>
          <Button size="lg" variant="secondary" icon="⌨" onClick={() => startOwn('text')} block>
            {t('welcome.type')}
          </Button>
        </section>

        <Card className="center">
          <h3>{t('welcome.demo')}</h3>
          <p className="muted">{t('welcome.demoHint')}</p>
          <Button
            size="lg"
            variant="secondary"
            icon="▶"
            onClick={() => demo.run()}
            loading={demo.pending}
          >
            {t('welcome.demo')}
          </Button>
          {demo.error ? (
            <p className="small" style={{ color: 'var(--red-700)', marginTop: 'var(--space-3)' }}>
              {demo.error}
            </p>
          ) : null}
          {isAuthenticated && user ? (
            <p className="tiny muted" style={{ marginTop: 'var(--space-3)' }}>
              Signed in as {user.full_name}
            </p>
          ) : null}
        </Card>

        <section className="card">
          <h3>{t('welcome.how')}</h3>
          <ol className="stack-sm" style={{ paddingLeft: '1.2rem', margin: 0 }}>
            <li>{t('welcome.step1')}</li>
            <li>{t('welcome.step2')}</li>
            <li>{t('welcome.step3')}</li>
            <li>{t('welcome.step4')}</li>
          </ol>
        </section>

        <Notice tone="info" title="About your information">
          <p style={{ margin: 0 }} className="small">
            {t('welcome.privacy')}
          </p>
        </Notice>

        {status ? (
          <section className="card card--quiet">
            <h4>What is real in this build</h4>
            <p className="small muted">
              We would rather tell you than let you assume. Voice recognition runs in your browser.
              {status.capabilities.llm_assisted_extraction
                ? ' Profile extraction is assisted by a language model.'
                : ' Profile extraction uses deterministic rules, not a language model.'}
              {status.capabilities.neural_embeddings
                ? ' Retrieval uses neural embeddings.'
                : ' Retrieval blends a local lexical vectoriser with keyword search and structured filters.'}
            </p>
            <p className="tiny muted" style={{ margin: 0 }}>
              <a href="/system">See every data source and integration status →</a>
            </p>
          </section>
        ) : null}
      </div>
    </Layout>
  )
}
