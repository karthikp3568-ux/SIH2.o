/**
 * Screen 1 → the conversation itself.
 *
 * Voice and text are equal paths, not a primary and a fallback. The recogniser's
 * confidence is forwarded to the backend; when it is low the backend asks for a
 * confirmation and we surface the transcript for correction rather than guessing.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { api } from '../api/client'
import { Layout } from '../components/Layout'
import { Button, Card, Chip, ErrorState, Loading, Notice } from '../components/ui'
import { useAction } from '../hooks/useAsync'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'
import { useApp } from '../state/AppContext'
import type { ConversationMessage, DraftProfile, Slot } from '../api/types'

interface Turn {
  role: 'assistant' | 'beneficiary'
  text: string
  meta?: string
}

export function Conversation() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const [params] = useSearchParams()
  const isDemo = params.get('demo') === '1'
  const navigate = useNavigate()
  const { t, language, speechTag } = useApp()

  const [turns, setTurns] = useState<Turn[]>([])
  const [pendingSlot, setPendingSlot] = useState<Slot | null>(null)
  const [draft, setDraft] = useState<DraftProfile>({})
  const [progress, setProgress] = useState(0)
  const [readyToConfirm, setReadyToConfirm] = useState(false)
  const [pendingTranscript, setPendingTranscript] = useState<string | null>(null)
  const [textInput, setTextInput] = useState('')
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [demoStep, setDemoStep] = useState(0)
  const [demoScript, setDemoScript] = useState<{ text: string; note: string }[]>([])

  const chatRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const send = useAction(
    async (text: string, options: { asrConfidence?: number; slotAnswer?: string } = {}) => {
      if (!conversationId) return undefined
      const response = await api.sendMessage(conversationId, {
        text,
        language,
        asr_confidence: options.asrConfidence,
        speech_provider: options.asrConfidence !== undefined ? 'browser_web_speech' : undefined,
        slot_answer: options.slotAnswer,
      })

      setTurns((current) => [
        ...current,
        {
          role: 'beneficiary',
          text,
          meta:
            options.asrConfidence !== undefined
              ? `heard with ${Math.round(options.asrConfidence * 100)}% confidence`
              : undefined,
        },
        { role: 'assistant', text: response.assistant_message },
      ])
      setPendingSlot(response.pending_slot)
      setDraft(response.draft_profile)
      setProgress(response.progress.percent ?? 0)
      setReadyToConfirm(response.ready_to_confirm)
      setPendingTranscript(response.needs_confirmation ? response.transcript_for_correction : null)
      return response
    },
  )

  const handleSpeech = useCallback(
    ({ transcript, confidence }: { transcript: string; confidence: number }) => {
      if (!transcript) return
      void send.run(transcript, { asrConfidence: confidence })
    },
    [send],
  )

  const speech = useSpeechRecognition(speechTag, handleSpeech)

  useEffect(() => {
    if (!conversationId) return
    setLoading(true)
    api
      .getConversation(conversationId)
      .then((conversation) => {
        setTurns(
          conversation.messages
            .filter((m: ConversationMessage) => m.role !== 'system')
            .map((m) => ({
              role: m.role === 'assistant' ? 'assistant' : 'beneficiary',
              text: m.raw_text,
              meta:
                m.asr_confidence !== null
                  ? `heard with ${Math.round(m.asr_confidence * 100)}% confidence`
                  : undefined,
            })),
        )
        setPendingSlot(conversation.pending_slot)
        setDraft(conversation.draft_profile)
        setProgress(conversation.progress?.percent ?? 0)
        setReadyToConfirm(conversation.state === 'awaiting_confirmation')
      })
      .catch((error: Error) => setLoadError(error.message))
      .finally(() => setLoading(false))
  }, [conversationId])

  useEffect(() => {
    if (!isDemo) return
    api
      .demoScript()
      .then((script) => setDemoScript(script.english ?? []))
      .catch(() => setDemoScript([]))
  }, [isDemo])

  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns])

  const submitText = (event: React.FormEvent) => {
    event.preventDefault()
    const text = textInput.trim()
    if (!text) return
    setTextInput('')
    void send.run(text)
  }

  const confirmTranscript = () => {
    if (!pendingTranscript) return
    const text = pendingTranscript
    setPendingTranscript(null)
    void send.run(text)
  }

  const correctTranscript = () => {
    setTextInput(pendingTranscript ?? '')
    setPendingTranscript(null)
    inputRef.current?.focus()
  }

  const answerSlot = (value: string, label: string) => {
    void send.run(label, { slotAnswer: value })
  }

  const playDemoStep = () => {
    const line = demoScript[demoStep]
    if (!line) return
    setDemoStep((step) => step + 1)
    void send.run(line.text)
  }

  if (loading) {
    return (
      <Layout>
        <Loading label={t('common.loading')} />
      </Layout>
    )
  }

  if (loadError) {
    return (
      <Layout>
        <ErrorState message={loadError} onRetry={() => navigate('/')} retryLabel={t('common.back')} />
      </Layout>
    )
  }

  return (
    <Layout>
      <div className="stack">
        <div className="row row--between">
          <h1 style={{ marginBottom: 0 }}>{t('conversation.title')}</h1>
          <Chip icon="◔">{`${t('conversation.progress')}: ${progress}%`}</Chip>
        </div>
        <div className="progress-bar" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
          <div className="progress-bar__fill" style={{ width: `${progress}%` }} />
        </div>

        {isDemo && demoScript.length > 0 ? (
          <Notice tone="info" title="Demo mode">
            <p className="small" style={{ marginBottom: 'var(--space-3)' }}>
              These are Ravi's own words. Everything the system shows afterwards is computed from
              them by the same code a live user goes through.
            </p>
            {demoStep < demoScript.length ? (
              <Button variant="secondary" icon="▶" onClick={playDemoStep} loading={send.pending}>
                Say line {demoStep + 1} of {demoScript.length}
              </Button>
            ) : (
              <p className="small strong" style={{ margin: 0 }}>
                Ravi has said everything. Continue below.
              </p>
            )}
          </Notice>
        ) : null}

        <div className="chat" ref={chatRef} role="log" aria-live="polite" aria-label="Conversation">
          {turns.map((turn, index) => (
            <div key={index} className={`bubble bubble--${turn.role}`}>
              {turn.text}
              {turn.meta ? <span className="bubble__meta">{turn.meta}</span> : null}
            </div>
          ))}
          {speech.interimTranscript ? (
            <div className="bubble bubble--beneficiary" style={{ opacity: 0.6 }}>
              {speech.interimTranscript}…
            </div>
          ) : null}
          {send.pending ? <Loading label="Understanding…" /> : null}
        </div>

        {pendingTranscript ? (
          <Notice tone="warn" title={t('conversation.heardLow')}>
            <p className="strong" style={{ fontSize: '1.05rem' }}>&ldquo;{pendingTranscript}&rdquo;</p>
            <div className="row">
              <Button icon="✓" onClick={confirmTranscript}>
                {t('conversation.useThis')}
              </Button>
              <Button variant="secondary" icon="✎" onClick={correctTranscript}>
                {t('conversation.editText')}
              </Button>
            </div>
          </Notice>
        ) : null}

        {pendingSlot && pendingSlot.options.length > 0 ? (
          <Card>
            <h3>{pendingSlot.question}</h3>
            {pendingSlot.help ? <p className="small muted">{pendingSlot.help}</p> : null}
            <div className="choice-grid">
              {pendingSlot.options.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className="choice"
                  onClick={() => answerSlot(option.value, option.label)}
                  disabled={send.pending}
                >
                  <span className="choice__icon" aria-hidden="true">
                    {option.icon === 'home'
                      ? '🏠'
                      : option.icon === 'bus'
                        ? '🚌'
                        : option.icon === 'train'
                          ? '🚆'
                          : option.icon === 'briefcase'
                            ? '💼'
                            : option.icon === 'tools'
                              ? '🛠️'
                              : option.icon === 'shop'
                                ? '🏪'
                                : option.icon === 'certificate'
                                  ? '🎓'
                                  : '•'}
                  </span>
                  <span>{option.label}</span>
                </button>
              ))}
            </div>
          </Card>
        ) : null}

        <Card>
          {!speech.supported ? (
            <Notice tone="warn">
              <p className="small" style={{ margin: 0 }}>
                {t('conversation.micUnsupported')}
              </p>
            </Notice>
          ) : null}
          {speech.error === 'not-allowed' ? (
            <Notice tone="warn">
              <p className="small" style={{ margin: 0 }}>
                {t('conversation.micDenied')}
              </p>
            </Notice>
          ) : null}
          {speech.error === 'no-speech' ? (
            <Notice tone="warn">
              <p className="small" style={{ margin: 0 }}>
                We did not hear anything. Try again, or type below.
              </p>
            </Notice>
          ) : null}

          <div className="row" style={{ marginBottom: 'var(--space-4)', marginTop: 'var(--space-3)' }}>
            {speech.supported ? (
              <button
                type="button"
                className="btn btn--mic btn--lg"
                data-listening={speech.listening}
                onClick={() => (speech.listening ? speech.stop() : speech.start())}
                disabled={send.pending}
              >
                <span aria-hidden="true">{speech.listening ? '■' : '🎙'}</span>
                {speech.listening ? t('conversation.stop') : t('conversation.tapToSpeak')}
              </button>
            ) : null}
            {speech.listening ? (
              <span className="muted small" role="status">
                {t('conversation.listening')}
              </span>
            ) : null}
          </div>

          <form onSubmit={submitText}>
            <label htmlFor="message">{t('conversation.placeholder')}</label>
            <textarea
              id="message"
              ref={inputRef}
              value={textInput}
              onChange={(event) => setTextInput(event.target.value)}
              placeholder={t('conversation.placeholder')}
              rows={3}
            />
            <div className="row row--between" style={{ marginTop: 'var(--space-3)' }}>
              <Button type="submit" icon="➤" loading={send.pending} disabled={!textInput.trim()}>
                {t('conversation.send')}
              </Button>
              {(readyToConfirm || (draft.skills?.length ?? 0) > 0) && conversationId ? (
                <Button
                  variant={readyToConfirm ? 'primary' : 'secondary'}
                  icon="✓"
                  onClick={() => navigate(`/confirm/${conversationId}`)}
                >
                  {t('conversation.done')}
                </Button>
              ) : null}
            </div>
          </form>

          {send.error ? (
            <p className="small" style={{ color: 'var(--red-700)', marginTop: 'var(--space-3)' }}>
              {send.error}
            </p>
          ) : null}
        </Card>
      </div>
    </Layout>
  )
}
