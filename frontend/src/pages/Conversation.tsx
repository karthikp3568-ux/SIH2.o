/**
 * The voice conversation — the core of the product.
 *
 * Voice and text are equal paths. The recogniser's confidence is forwarded to
 * the backend; when it is low the backend asks for confirmation and we show
 * the transcript for correction rather than guessing. Every fact the system
 * extracts is shown against the sentence it came from.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import type { ConversationMessage, DraftProfile, Slot, UnderstoodFact } from '../api/types'
import { ConversationCard } from '../components/ConversationCard'
import type { Turn } from '../components/ConversationCard'
import { Icon } from '../components/Icon'
import type { IconName } from '../components/Icon'
import { Layout } from '../components/Layout'
import { Button, Chip, ErrorState, Loading } from '../components/ui'
import { VoiceOrb } from '../components/voice/VoiceOrb'
import type { VoiceState } from '../components/voice/VoiceOrb'
import { useMicAnalyser } from '../hooks/useMicAnalyser'
import { useSpeaker } from '../hooks/useSpeaker'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'
import { LANGUAGE_NAME } from '../lib/labels'
import { useApp } from '../state/AppContext'

const SLOT_ICON: Record<string, IconName> = {
  home: 'home',
  bus: 'bus',
  train: 'train',
  briefcase: 'briefcase',
  tools: 'wrench',
  shop: 'store',
  certificate: 'cap',
}

/** A fresh id per utterance, so a double-fired event cannot become two turns. */
function newMessageId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `m-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

const TRACKED: { key: string; label: string; icon: IconName; has: (d: DraftProfile) => boolean }[] = [
  { key: 'work', label: 'Work', icon: 'sprout', has: (d) => (d.occupations?.length ?? 0) > 0 },
  { key: 'skills', label: 'Skills', icon: 'wrench', has: (d) => (d.skills ?? []).some((s) => !s.is_category) },
  { key: 'education', label: 'Education', icon: 'cap', has: (d) => Boolean(d.education?.value) },
  { key: 'interests', label: 'Interests', icon: 'target', has: (d) => (d.interests?.length ?? 0) > 0 },
  { key: 'goal', label: 'Goal', icon: 'flag', has: (d) => (d.goals?.length ?? 0) > 0 },
  { key: 'travel', label: 'Travel', icon: 'bus', has: (d) => Boolean(d.mobility?.value) },
]

let turnSeq = 0
const nextId = () => `t${(turnSeq += 1)}`

export function Conversation() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const [params] = useSearchParams()
  const isGuided = params.get('demo') === '1'
  const mode = params.get('mode')
  const navigate = useNavigate()
  const { t, language, speechTag, user } = useApp()

  const [turns, setTurns] = useState<Turn[]>([])
  const [liveIds, setLiveIds] = useState<Set<string>>(new Set())
  const [pendingSlot, setPendingSlot] = useState<Slot | null>(null)
  const [draft, setDraft] = useState<DraftProfile>({})
  const [readyToConfirm, setReadyToConfirm] = useState(false)
  const [pendingTranscript, setPendingTranscript] = useState<string | null>(null)
  const [textInput, setTextInput] = useState('')
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [detected, setDetected] = useState<{ language: string | null; confidence: number | null; heard: number | null } | null>(null)
  /** What the last answer added, shown as "Added: …" until the next answer. */
  const [lastAdded, setLastAdded] = useState<UnderstoodFact[]>([])
  const [clarifying, setClarifying] = useState(false)
  /** Server id of the low-confidence message awaiting confirmation. */
  const [pendingMessageId, setPendingMessageId] = useState<string | null>(null)
  const [readAloud, setReadAloud] = useState(mode !== 'text')
  const [script, setScript] = useState<{ text: string; note: string }[]>([])
  const [scriptStep, setScriptStep] = useState(0)
  const [playback, setPlayback] = useState<string | null>(null)

  const inputRef = useRef<HTMLTextAreaElement>(null)
  const streamRef = useRef<HTMLDivElement>(null)
  const autoListened = useRef(false)
  /** Guards against a second submission while one is in flight. */
  const inFlight = useRef(false)

  const speaker = useSpeaker()

  const send = useCallback(
    async (
      text: string,
      options: { asrConfidence?: number; slotAnswer?: string; confirmMessageId?: string } = {},
    ) => {
      if (!conversationId || !text.trim() || inFlight.current) return
      inFlight.current = true
      setSending(true)
      setSendError(null)
      setLastAdded([])
      try {
        const response = await api.sendMessage(conversationId, {
          text,
          language,
          asr_confidence: options.asrConfidence,
          speech_provider: options.asrConfidence !== undefined ? 'browser_web_speech' : undefined,
          slot_answer: options.slotAnswer,
          client_message_id: newMessageId(),
          confirm_message_id: options.confirmMessageId,
        })
        const extraction = response.extraction as { language?: string; language_confidence?: number } | null
        const added = response.profile_update.map((fact) => fact.label)
        const assistantTurn: Turn = {
          id: nextId(),
          role: 'assistant',
          text: response.next_question || response.assistant_message,
        }
        if (options.confirmMessageId) {
          // The confirmed transcript is the turn already on screen: update it.
          setTurns((current) => {
            const index = current.findIndex((turn) => turn.serverId === options.confirmMessageId)
            if (index < 0) return [...current, assistantTurn]
            const updated = [...current]
            updated[index] = { ...updated[index], text, extracted: added }
            return [...updated, assistantTurn]
          })
          setLiveIds((current) => new Set([...current, assistantTurn.id]))
        } else {
          const userTurn: Turn = {
            id: nextId(),
            serverId: response.message_id,
            role: 'beneficiary',
            text,
            extracted: added,
            heardConfidence: options.asrConfidence ?? null,
            language: extraction?.language ?? null,
          }
          setTurns((current) => [...current, userTurn, assistantTurn])
          setLiveIds((current) => new Set([...current, userTurn.id, assistantTurn.id]))
        }
        setDetected({
          language: extraction?.language ?? null,
          confidence: extraction?.language_confidence ?? null,
          heard: options.asrConfidence ?? null,
        })
        setLastAdded(response.profile_update)
        setClarifying(response.clarification)
        setPendingSlot(response.pending_slot)
        setDraft(response.draft_profile ?? {})
        setReadyToConfirm(response.ready_to_confirm)
        setPendingTranscript(response.needs_confirmation ? response.transcript_for_correction : null)
        setPendingMessageId(response.needs_confirmation ? response.message_id : null)
      } catch (error) {
        setSendError(
          error instanceof ApiError && error.status === 0
            ? 'We could not reach the server. Check your connection — you can keep typing and send again.'
            : 'We’re having trouble processing your response. You can continue by typing.',
        )
        setTextInput(text)
      } finally {
        inFlight.current = false
        setSending(false)
      }
    },
    [conversationId, language],
  )

  const handleSpeech = useCallback(
    ({ transcript, confidence }: { transcript: string; confidence: number }) => {
      if (transcript) void send(transcript, { asrConfidence: confidence })
    },
    [send],
  )

  const speech = useSpeechRecognition(speechTag, handleSpeech)
  const mic = useMicAnalyser(speech.listening)

  const startListening = useCallback(() => {
    speaker.cancel()
    setSendError(null)
    setPendingTranscript(null)
    setPendingMessageId(null)
    setLastAdded([])
    speech.start()
  }, [speaker, speech])

  // --- load -----------------------------------------------------------------
  useEffect(() => {
    if (!conversationId) return
    setLoading(true)
    api
      .getConversation(conversationId)
      .then((conversation) => {
        if (conversation.state === 'confirmed') {
          navigate(`/confirm/${conversationId}`, { replace: true })
          return
        }
        setTurns(
          conversation.messages
            .filter((m: ConversationMessage) => m.role !== 'system')
            .map((m) => ({
              id: nextId(),
              serverId: m.id,
              role: m.role === 'assistant' ? 'assistant' : 'beneficiary',
              text: m.raw_text,
              heardConfidence: m.asr_confidence,
              language: m.detected_language,
            })),
        )
        setPendingSlot(conversation.pending_slot)
        setDraft(conversation.draft_profile ?? {})
        setReadyToConfirm(conversation.state === 'awaiting_confirmation')
      })
      .catch(() => setLoadError('We could not open this conversation.'))
      .finally(() => setLoading(false))
  }, [conversationId, navigate])

  useEffect(() => {
    if (!isGuided) return
    api
      .demoScript()
      .then((data) =>
        setScript(
          language === 'kn' && data.kannada?.length
            ? data.kannada
            : language === 'hi' && data.hindi?.length
              ? data.hindi
              : data.english ?? [],
        ),
      )
      .catch(() => setScript([]))
  }, [isGuided, language])

  // Start listening straight away when the person chose to talk.
  useEffect(() => {
    if (loading || autoListened.current || mode !== 'voice' || !speech.supported) return
    autoListened.current = true
    startListening()
  }, [loading, mode, speech.supported, startListening])

  useEffect(() => {
    if (!loading && mode === 'text') inputRef.current?.focus()
  }, [loading, mode])

  const lastAssistant = useMemo(() => [...turns].reverse().find((turn) => turn.role === 'assistant'), [turns])

  // Read each new question aloud when the person asked for it.
  const spokenRef = useRef<string | null>(null)
  useEffect(() => {
    if (!readAloud || !lastAssistant || spokenRef.current === lastAssistant.id) return
    spokenRef.current = lastAssistant.id
    speaker.speak(lastAssistant.text, speechTag)
  }, [readAloud, lastAssistant, speaker, speechTag])

  useEffect(() => {
    const el = streamRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [turns])

  // --- actions ----------------------------------------------------------------
  const submitText = (event: React.FormEvent) => {
    event.preventDefault()
    const text = textInput.trim()
    if (!text) return
    setTextInput('')
    void send(text)
  }

  const confirmTranscript = () => {
    if (!pendingTranscript) return
    const text = pendingTranscript
    const messageId = pendingMessageId
    setPendingTranscript(null)
    setPendingMessageId(null)
    void send(text, { confirmMessageId: messageId ?? undefined })
  }

  const typeInstead = () => {
    setTextInput(pendingTranscript ?? '')
    setPendingTranscript(null)
    setPendingMessageId(null)
    requestAnimationFrame(() => inputRef.current?.focus())
  }

  const playScriptLine = () => {
    const line = script[scriptStep]
    if (!line || playback !== null) return
    setScriptStep((step) => step + 1)
    const words = line.text.split(' ')
    let shown = 0
    setPlayback('')
    const timer = window.setInterval(() => {
      shown += 1
      setPlayback(words.slice(0, shown).join(' '))
      if (shown >= words.length) {
        window.clearInterval(timer)
        window.setTimeout(() => {
          setPlayback(null)
          void send(line.text)
        }, 350)
      }
    }, 70)
  }

  // --- render -------------------------------------------------------------------
  if (loading) {
    return (
      <Layout>
        <Loading label="Opening your conversation…" />
      </Layout>
    )
  }
  if (loadError) {
    return (
      <Layout>
        <ErrorState message={loadError} onRetry={() => navigate('/')} retryLabel="Back to start" />
      </Layout>
    )
  }

  const orbState: VoiceState = sending
    ? 'processing'
    : speech.listening
      ? 'listening'
      : speaker.speaking
        ? 'speaking'
        : 'idle'
  const liveTranscript = playback ?? speech.interimTranscript
  const canReview = readyToConfirm || (draft.skills?.length ?? 0) > 0
  const question = lastAssistant?.text ?? t('conversation.title')
  const history = turns.slice(0, lastAssistant ? turns.lastIndexOf(lastAssistant) : turns.length)

  const statusLine = sending
    ? 'Understanding your response…'
    : speech.listening
      ? t('conversation.listening')
      : speaker.speaking
        ? 'Reading the question aloud…'
        : playback !== null
          ? 'Playing Ravi’s words…'
          : speech.supported
            ? 'Tap the microphone to answer'
            : 'Type your answer below'

  return (
    <Layout bare>
      <div className="container talk">
        {/* ---- Stage: the orb and microphone ---- */}
        <aside className="talk__stage" aria-label="Voice">
          <div className="talk__orb">
            <VoiceOrb
              state={orbState}
              getLevel={speech.listening ? mic.getLevel : speaker.getLevel}
              getBands={mic.getBands}
              size={280}
              label={statusLine}
            />
          </div>
          <p className="talk__status" role="status" aria-live="polite">
            {statusLine}
          </p>

          {speech.supported ? (
            <button
              type="button"
              className={`mic-button ${speech.listening ? 'mic-button--on' : ''}`}
              onClick={() => (speech.listening ? speech.stop() : startListening())}
              disabled={sending || playback !== null}
              aria-pressed={speech.listening}
            >
              <Icon name={speech.listening ? 'stop' : 'mic'} size={26} />
              <span>{speech.listening ? t('conversation.stop') : t('conversation.tapToSpeak')}</span>
            </button>
          ) : null}

          <div className="talk__signals">
            {detected?.language ? (
              <Chip icon="globe">Detected: {LANGUAGE_NAME[detected.language] ?? detected.language}</Chip>
            ) : (
              <Chip icon="globe">Speaking: {LANGUAGE_NAME[language] ?? language}</Chip>
            )}
            {detected?.heard !== null && detected?.heard !== undefined ? (
              <Chip icon="mic" tone={detected.heard >= 0.7 ? 'good' : 'warn'}>
                Heard with {Math.round(detected.heard * 100)}% confidence
              </Chip>
            ) : null}
            {speaker.supported ? (
              <button
                type="button"
                className="chip chip--outline talk__toggle"
                aria-pressed={readAloud}
                onClick={() => {
                  if (readAloud) speaker.cancel()
                  setReadAloud((value) => !value)
                }}
              >
                <Icon name={readAloud ? 'volume' : 'volumeOff'} size={14} />
                {readAloud ? 'Reading questions aloud' : 'Read questions aloud'}
              </button>
            ) : null}
          </div>
        </aside>

        {/* ---- Main: the current question ---- */}
        <section className="talk__main" aria-labelledby="current-question">
          <ul className="understood-track" aria-label="What we have understood so far">
            {TRACKED.map((item) => {
              const done = item.has(draft)
              return (
                <li key={item.key} className={done ? 'is-done' : ''}>
                  <Icon name={done ? 'check' : item.icon} size={14} strokeWidth={done ? 3 : 2} />
                  {item.label}
                  <span className="visually-hidden">{done ? ' — understood' : ' — not yet'}</span>
                </li>
              )
            })}
          </ul>

          {lastAdded.length > 0 && !sending ? (
            <div className="added-strip" role="status" aria-label="Added to your profile">
              <span className="added-strip__label">
                <Icon name="checkCircle" size={16} /> Added
              </span>
              {lastAdded.map((fact, index) => (
                <span key={`${fact.slot}-${fact.label}`} className="added-strip__chip pop" style={{ animationDelay: `${index * 140}ms` }}>
                  <Icon name="plus" size={12} strokeWidth={3} />
                  {fact.label}
                </span>
              ))}
            </div>
          ) : null}

          <div className={`question-card ${clarifying ? 'question-card--retry' : ''}`} key={lastAssistant?.id}>
            <span className="eyebrow">
              {clarifying ? (
                <>
                  <Icon name="refresh" size={14} /> Let’s try that another way
                </>
              ) : (
                <>
                  <Icon name="compass" size={14} /> {user?.full_name ? `For ${user.full_name.split(' ')[0]}` : 'Question'}
                </>
              )}
            </span>
            <h1 id="current-question" className="question-card__text">
              {question}
            </h1>
            <p className="question-card__hint">
              {pendingSlot?.help ?? 'You can speak naturally. No need to fill out a form.'}
            </p>
          </div>

          {liveTranscript ? (
            <div className="live-transcript" aria-live="polite">
              <span className="eyebrow">{playback !== null ? 'Ravi says' : 'Hearing'}</span>
              <p>
                {liveTranscript}
                <span className="live-transcript__caret" aria-hidden="true" />
              </p>
            </div>
          ) : null}

          {speech.error === 'no-speech' || speech.error === 'network' || speech.error === 'other' ? (
            <ErrorState
              title="We couldn’t hear that clearly."
              message={
                speech.error === 'network'
                  ? 'Voice recognition needs a connection right now. You can try again, or type below.'
                  : 'Try again a little closer to the microphone, or type your answer below.'
              }
              onRetry={startListening}
            />
          ) : null}
          {speech.error === 'not-allowed' ? (
            <ErrorState title="Microphone is blocked" message={t('conversation.micDenied')} />
          ) : null}

          {pendingTranscript ? (
            <div className="confirm-card enter" role="alert">
              <span className="eyebrow">
                <Icon name="alert" size={14} /> I’m not sure I heard that clearly
              </span>
              <p className="confirm-card__quote">“{pendingTranscript}”</p>
              <p className="small muted" style={{ margin: '0 0 var(--space-3)' }}>
                Is this what you said?
              </p>
              <div className="row">
                <Button icon="check" onClick={confirmTranscript} disabled={sending}>
                  Yes, that’s right
                </Button>
                {speech.supported ? (
                  <Button variant="secondary" icon="mic" onClick={startListening} disabled={sending}>
                    Try again
                  </Button>
                ) : null}
                <Button variant="ghost" icon="keyboard" onClick={typeInstead} disabled={sending}>
                  Type instead
                </Button>
              </div>
            </div>
          ) : null}

          {pendingSlot && pendingSlot.options.length > 0 && !pendingTranscript ? (
            <div className="slot-options" role="group" aria-label={pendingSlot.question}>
              {pendingSlot.options.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className="choice"
                  onClick={() => void send(option.label, { slotAnswer: option.value })}
                  disabled={sending}
                >
                  <span className="icon-tile icon-tile--sm icon-tile--blue">
                    <Icon name={SLOT_ICON[option.icon ?? ''] ?? 'chevronRight'} size={18} />
                  </span>
                  {option.label}
                </button>
              ))}
            </div>
          ) : null}

          {isGuided && script.length > 0 ? (
            <div className="presenter">
              <div className="grow">
                <span className="eyebrow">
                  <Icon name="play" size={12} /> Guided example
                </span>
                <p className="small" style={{ margin: '4px 0 0' }}>
                  {scriptStep < script.length
                    ? `Play Ravi’s own words (${scriptStep + 1} of ${script.length}). Everything after is computed live.`
                    : 'Ravi has said everything. Review what we understood.'}
                </p>
              </div>
              {scriptStep < script.length ? (
                <Button variant="dark" size="sm" icon="play" onClick={playScriptLine} disabled={sending || playback !== null}>
                  Play line {scriptStep + 1}
                </Button>
              ) : null}
            </div>
          ) : null}

          <form className="composer" onSubmit={submitText}>
            <label htmlFor="message" className="visually-hidden">
              {t('conversation.placeholder')}
            </label>
            <textarea
              id="message"
              ref={inputRef}
              value={textInput}
              onChange={(event) => setTextInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  event.currentTarget.form?.requestSubmit()
                }
              }}
              placeholder="Or type your answer here…"
              rows={2}
            />
            <Button type="submit" icon="send" loading={sending} disabled={!textInput.trim()} aria-label={t('conversation.send')}>
              <span className="composer__send-label">{t('conversation.send')}</span>
            </Button>
          </form>

          {sendError ? <ErrorState title="That did not go through" message={sendError} /> : null}

          {canReview && conversationId ? (
            <div className={`continue-bar ${readyToConfirm ? 'continue-bar--ready' : ''}`}>
              <div className="grow">
                <strong>{readyToConfirm ? 'We have what we need.' : 'You can review at any time.'}</strong>
                <div className="small muted">See what we understood, and correct anything before we continue.</div>
              </div>
              <Button
                variant={readyToConfirm ? 'primary' : 'secondary'}
                iconRight="arrowRight"
                onClick={() => {
                  speech.stop()
                  speaker.cancel()
                  navigate(`/confirm/${conversationId}`)
                }}
              >
                Review what we understood
              </Button>
            </div>
          ) : null}
        </section>

        {/* ---- Side: the conversation so far ---- */}
        <aside className="talk__side" aria-label="Conversation so far">
          <h2 className="eyebrow" style={{ marginBottom: 'var(--space-3)' }}>
            Conversation so far
          </h2>
          <div className="talk__stream" ref={streamRef} role="log" aria-live="polite">
            {history.length === 0 ? (
              <p className="small muted">Your answers and what we understood from them will appear here.</p>
            ) : (
              history.map((turn) => <ConversationCard key={turn.id} turn={turn} animate={liveIds.has(turn.id)} />)
            )}
            {sending ? (
              <div className="convo-card convo-card--thinking" aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
            ) : null}
          </div>
        </aside>
      </div>
    </Layout>
  )
}
