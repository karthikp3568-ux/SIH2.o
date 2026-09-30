/** Starts (or resumes) a conversation, then hands over to the chat screen. */

import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '../api/client'
import { Layout } from '../components/Layout'
import { ErrorState, Loading } from '../components/ui'
import { useApp } from '../state/AppContext'

export function Start() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { language, t } = useApp()
  const [error, setError] = useState<string | null>(null)
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    api
      .startConversation({
        language,
        channel: params.get('mode') === 'voice' ? 'web_voice' : 'web_text',
        resume: params.get('fresh') !== '1',
      })
      .then((session) => navigate(`/conversation/${session.conversation.id}`, { replace: true }))
      .catch((caught: Error) => setError(caught.message))
  }, [language, navigate, params])

  return (
    <Layout>
      {error ? (
        <ErrorState message={error} onRetry={() => navigate('/')} retryLabel={t('common.back')} />
      ) : (
        <Loading label={t('common.loading')} />
      )}
    </Layout>
  )
}
