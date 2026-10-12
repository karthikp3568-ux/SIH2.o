/**
 * Browser speech recognition via the Web Speech API.
 *
 * This is real multilingual ASR, running on the device in Chrome and Edge. It
 * is not available in Firefox or in some in-app browsers, which is why every
 * screen that uses it also offers text input — not as a downgrade but as an
 * equal path.
 *
 * Uses continuous listening with a 2.8-second silence detector:
 * The microphone stays listening continuously while the person speaks. It only
 * finalises and submits when there has been ~3 seconds of continuous silence,
 * or when the user explicitly taps Stop.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

interface SpeechRecognitionResultLike {
  transcript: string
  confidence: number
}

interface UseSpeechRecognition {
  supported: boolean
  listening: boolean
  interimTranscript: string
  error: 'not-allowed' | 'no-speech' | 'network' | 'unsupported' | 'other' | null
  start: () => void
  stop: () => void
}

type Handler = (result: SpeechRecognitionResultLike) => void

const SILENCE_TIMEOUT_MS = 2800 // ~3 seconds of silence before finishing turn

function getRecognitionConstructor(): any | null {
  if (typeof window === 'undefined') return null
  const anyWindow = window as any
  return anyWindow.SpeechRecognition ?? anyWindow.webkitSpeechRecognition ?? null
}

export function useSpeechRecognition(languageTag: string, onResult: Handler): UseSpeechRecognition {
  const [listening, setListening] = useState(false)
  const [interimTranscript, setInterim] = useState('')
  const [error, setError] = useState<UseSpeechRecognition['error']>(null)
  
  const recognitionRef = useRef<any>(null)
  const onResultRef = useRef(onResult)
  const silenceTimerRef = useRef<any>(null)
  const desiredListeningRef = useRef(false)
  const deliveredRef = useRef(false)
  const finalTranscriptRef = useRef('')
  const currentConfidenceRef = useRef(0.85)

  const supported = getRecognitionConstructor() !== null

  useEffect(() => {
    onResultRef.current = onResult
  }, [onResult])

  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
  }, [])

  const deliverIfReady = useCallback(() => {
    clearSilenceTimer()
    const text = (finalTranscriptRef.current || '').trim()
    if (!deliveredRef.current && text.length > 0) {
      deliveredRef.current = true
      onResultRef.current({
        transcript: text,
        confidence: currentConfidenceRef.current,
      })
    }
    finalTranscriptRef.current = ''
    setInterim('')
  }, [clearSilenceTimer])

  const stop = useCallback(() => {
    desiredListeningRef.current = false
    clearSilenceTimer()

    const text = (finalTranscriptRef.current || '').trim()
    if (!deliveredRef.current && text.length > 0) {
      deliveredRef.current = true
      onResultRef.current({
        transcript: text,
        confidence: currentConfidenceRef.current,
      })
    }

    const recognition = recognitionRef.current
    if (recognition) {
      try {
        recognition.stop()
      } catch {
        /* already stopped */
      }
    }

    setListening(false)
    setInterim('')
    finalTranscriptRef.current = ''
  }, [clearSilenceTimer])

  const start = useCallback(() => {
    const Constructor = getRecognitionConstructor()
    if (!Constructor) {
      setError('unsupported')
      return
    }

    // Reset state for new utterance
    clearSilenceTimer()
    deliveredRef.current = false
    finalTranscriptRef.current = ''
    currentConfidenceRef.current = 0.85
    desiredListeningRef.current = true
    setError(null)
    setInterim('')

    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort()
      } catch {
        /* ignore */
      }
    }

    const recognition = new Constructor()
    recognition.lang = languageTag
    recognition.interimResults = true
    recognition.continuous = true
    recognition.maxAlternatives = 3

    const isCurrent = () => recognitionRef.current === recognition

    recognition.onstart = () => {
      if (isCurrent()) {
        setListening(true)
      }
    }

    recognition.onresult = (event: any) => {
      if (!isCurrent() || deliveredRef.current) return

      let accumulatedFinal = ''
      let interim = ''

      for (let i = 0; i < event.results.length; i += 1) {
        const result = event.results[i]
        const alternative = result[0]
        if (!alternative) continue

        if (typeof alternative.confidence === 'number' && alternative.confidence > 0) {
          currentConfidenceRef.current = alternative.confidence
        }

        if (result.isFinal) {
          accumulatedFinal += (accumulatedFinal ? ' ' : '') + (alternative.transcript || '').trim()
        } else {
          interim += (interim ? ' ' : '') + (alternative.transcript || '').trim()
        }
      }

      const combined = [accumulatedFinal, interim].filter(Boolean).join(' ').trim()
      finalTranscriptRef.current = combined
      setInterim(combined)

      // User just spoke: reset the 2.8s silence timer
      clearSilenceTimer()

      if (combined.length > 0 && desiredListeningRef.current) {
        silenceTimerRef.current = setTimeout(() => {
          if (isCurrent() && desiredListeningRef.current && !deliveredRef.current) {
            desiredListeningRef.current = false
            deliverIfReady()
            try {
              recognition.stop()
            } catch {
              /* ignore */
            }
            setListening(false)
          }
        }, SILENCE_TIMEOUT_MS)
      }
    }

    recognition.onerror = (event: any) => {
      if (!isCurrent()) return
      const code = String(event?.error ?? 'other')
      if (code === 'not-allowed' || code === 'service-not-allowed') {
        desiredListeningRef.current = false
        setError('not-allowed')
        setListening(false)
      } else if (code === 'no-speech') {
        // Just ambient silence; keep listening if user still intends to speak
      } else if (code === 'network') {
        desiredListeningRef.current = false
        setError('network')
        setListening(false)
      } else if (code !== 'aborted') {
        setError('other')
      }
    }

    recognition.onend = () => {
      if (!isCurrent()) return
      // If user still wants to listen and hasn't delivered, auto-restart
      if (desiredListeningRef.current && !deliveredRef.current) {
        try {
          recognition.start()
          return
        } catch {
          /* fall through */
        }
      }
      setListening(false)
      setInterim('')
    }

    recognitionRef.current = recognition
    try {
      recognition.start()
    } catch {
      setError('other')
      setListening(false)
    }
  }, [clearSilenceTimer, deliverIfReady, languageTag])

  useEffect(() => {
    return () => {
      desiredListeningRef.current = false
      clearSilenceTimer()
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort()
        } catch {
          /* ignore */
        }
      }
    }
  }, [clearSilenceTimer])

  return { supported, listening, interimTranscript, error, start, stop }
}
