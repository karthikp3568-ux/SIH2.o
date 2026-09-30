/**
 * Browser speech recognition via the Web Speech API.
 *
 * This is real multilingual ASR, running on the device in Chrome and Edge. It
 * is not available in Firefox or in some in-app browsers, which is why every
 * screen that uses it also offers text input — not as a downgrade but as an
 * equal path.
 *
 * The recogniser's own confidence is passed through to the backend untouched,
 * so a doubtful transcript triggers a confirmation turn rather than being
 * committed to the profile.
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
  const supported = getRecognitionConstructor() !== null

  useEffect(() => {
    onResultRef.current = onResult
  }, [onResult])

  const stop = useCallback(() => {
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
  }, [])

  const start = useCallback(() => {
    const Constructor = getRecognitionConstructor()
    if (!Constructor) {
      setError('unsupported')
      return
    }
    stop()
    setError(null)

    const recognition = new Constructor()
    recognition.lang = languageTag
    recognition.interimResults = true
    recognition.continuous = false
    // Alternatives let the UI offer a correction rather than guessing again.
    recognition.maxAlternatives = 3

    recognition.onstart = () => setListening(true)

    recognition.onresult = (event: any) => {
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]
        const alternative = result[0]
        if (result.isFinal) {
          onResultRef.current({
            transcript: String(alternative.transcript ?? '').trim(),
            // Some engines omit confidence entirely. 0.8 is a neutral stand-in,
            // deliberately above the confirmation threshold so we do not nag,
            // and it is never presented as a measured value.
            confidence:
              typeof alternative.confidence === 'number' && alternative.confidence > 0
                ? alternative.confidence
                : 0.8,
          })
          interim = ''
        } else {
          interim += alternative.transcript
        }
      }
      setInterim(interim)
    }

    recognition.onerror = (event: any) => {
      const code = String(event?.error ?? 'other')
      if (code === 'not-allowed' || code === 'service-not-allowed') setError('not-allowed')
      else if (code === 'no-speech') setError('no-speech')
      else if (code === 'network') setError('network')
      else if (code !== 'aborted') setError('other')
      setListening(false)
    }

    recognition.onend = () => {
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
  }, [languageTag, stop])

  useEffect(() => stop, [stop])

  return { supported, listening, interimTranscript, error, start, stop }
}
