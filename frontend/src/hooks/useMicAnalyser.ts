/**
 * Live microphone level for the voice visualisation.
 *
 * Runs alongside the browser recogniser (both can read the same microphone).
 * Nothing is recorded or sent anywhere: the stream feeds an AnalyserNode and
 * is stopped the moment listening ends. If the microphone cannot be opened the
 * visual simply stays calm — recognition and typing still work.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export interface MicAnalyser {
  /** Smoothed loudness, 0..1. */
  getLevel: () => number
  /** `count` frequency bands, each 0..1, low to high. */
  getBands: (count: number) => number[]
  available: boolean
}

export function useMicAnalyser(active: boolean): MicAnalyser {
  const [available, setAvailable] = useState(false)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const bufferRef = useRef<Uint8Array | null>(null)
  const freqRef = useRef<Uint8Array | null>(null)
  const levelRef = useRef(0)

  useEffect(() => {
    if (!active) return
    let cancelled = false
    let stream: MediaStream | null = null
    let context: AudioContext | null = null

    const open = async () => {
      if (!navigator.mediaDevices?.getUserMedia) return
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }
        const AudioContextCtor = window.AudioContext ?? (window as any).webkitAudioContext
        context = new AudioContextCtor() as AudioContext
        if (context.state === 'suspended') await context.resume().catch(() => undefined)
        const source = context.createMediaStreamSource(stream)
        const analyser = context.createAnalyser()
        analyser.fftSize = 512
        analyser.smoothingTimeConstant = 0.72
        source.connect(analyser)
        analyserRef.current = analyser
        bufferRef.current = new Uint8Array(analyser.fftSize)
        freqRef.current = new Uint8Array(analyser.frequencyBinCount)
        setAvailable(true)
      } catch {
        setAvailable(false)
      }
    }
    void open()

    return () => {
      cancelled = true
      analyserRef.current = null
      levelRef.current = 0
      setAvailable(false)
      stream?.getTracks().forEach((track) => track.stop())
      void context?.close().catch(() => undefined)
    }
  }, [active])

  const getLevel = useCallback(() => {
    const analyser = analyserRef.current
    const buffer = bufferRef.current
    if (!analyser || !buffer) {
      levelRef.current *= 0.9
      return levelRef.current
    }
    analyser.getByteTimeDomainData(buffer as any)
    let sum = 0
    for (let i = 0; i < buffer.length; i += 1) {
      const centred = (buffer[i] - 128) / 128
      sum += centred * centred
    }
    const rms = Math.sqrt(sum / buffer.length)
    // Speech RMS rarely exceeds ~0.3; map to a usable 0..1 range.
    const target = Math.min(1, rms * 3.6)
    levelRef.current = levelRef.current * 0.7 + target * 0.3
    return levelRef.current
  }, [])

  const getBands = useCallback((count: number) => {
    const analyser = analyserRef.current
    const freq = freqRef.current
    if (!analyser || !freq) return new Array(count).fill(0)
    analyser.getByteFrequencyData(freq as any)
    // Voice energy sits in the lower third of the spectrum.
    const usable = Math.floor(freq.length * 0.4)
    const size = Math.max(1, Math.floor(usable / count))
    const bands: number[] = []
    for (let b = 0; b < count; b += 1) {
      let total = 0
      for (let i = b * size; i < (b + 1) * size; i += 1) total += freq[i] ?? 0
      bands.push(Math.min(1, total / size / 200))
    }
    return bands
  }, [])

  return { getLevel, getBands, available }
}
