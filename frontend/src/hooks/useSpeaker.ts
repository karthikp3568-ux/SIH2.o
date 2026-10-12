/**
 * Reads assistant questions aloud with the browser's speech synthesis.
 *
 * Synthesis exposes no audio stream, so the visual "level" is driven by the
 * engine's own word-boundary events: each spoken word produces a pulse that
 * decays. The orb therefore moves only while words are actually being spoken.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export interface Speaker {
  supported: boolean
  speaking: boolean
  speak: (text: string, languageTag: string) => void
  cancel: () => void
  getLevel: () => number
}

export function useSpeaker(): Speaker {
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window
  const [speaking, setSpeaking] = useState(false)
  const pulseRef = useRef(0)

  const cancel = useCallback(() => {
    if (!supported) return
    window.speechSynthesis.cancel()
    setSpeaking(false)
  }, [supported])

  const speak = useCallback(
    (text: string, languageTag: string) => {
      if (!supported || !text) return
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.lang = languageTag
      utterance.rate = 0.98
      const voice = window.speechSynthesis
        .getVoices()
        .find((v) => v.lang?.toLowerCase().startsWith(languageTag.slice(0, 2).toLowerCase()))
      if (voice) utterance.voice = voice
      utterance.onstart = () => {
        setSpeaking(true)
        pulseRef.current = 0.6
      }
      utterance.onboundary = () => {
        pulseRef.current = 0.55 + Math.random() * 0.4
      }
      utterance.onend = () => setSpeaking(false)
      utterance.onerror = () => setSpeaking(false)
      window.speechSynthesis.speak(utterance)
    },
    [supported],
  )

  const getLevel = useCallback(() => {
    pulseRef.current *= 0.93
    return pulseRef.current
  }, [])

  useEffect(() => cancel, [cancel])

  return { supported, speaking, speak, cancel, getLevel }
}
