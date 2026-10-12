/** Starts (or resumes) a conversation, then hands over to the conversation screen. */

import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '../api/client'
import { Layout } from '../components/Layout'
import { ErrorState, Loading } from '../components/ui'
import { useApp } from '../state/AppContext'

export function Start() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { language } = useApp()
  const [error, setError] = useState<string | null>(null)
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    const mode = params.get('mode') === 'text' ? 'text' : 'voice'
    api
      .startConversation({
        language,
        channel: mode === 'voice' ? 'web_voice' : 'web_text',
        resume: params.get('fresh') !== '1',
      })
      .then((session) => navigate(`/conversation/${session.conversation.id}?mode=${mode}`, { replace: true }))
      .catch(() => setError('We could not start a conversation right now. Please try again in a moment.'))
  }, [language, navigate, params])

  return (
    <Layout>
      {error ? (
        <ErrorState message={error} onRetry={() => navigate('/')} retryLabel="Back to start" />
      ) : (
        <Loading label="Getting ready to listen…" />
      )}
    </Layout>
  )
}
