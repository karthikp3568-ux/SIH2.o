/**
 * The voice orb.
 *
 * Its motion is a readout, not decoration:
 *   idle        slow breathing — the system is ready
 *   listening   radius and bars follow the live microphone level
 *   processing  a single arc travels the ring — a request is in flight
 *   speaking    pulses on each word the synthesiser speaks
 *
 * Animation runs in a requestAnimationFrame loop that writes straight to SVG
 * attributes, so a 60fps readout never re-renders React.
 */

import { useEffect, useRef } from 'react'

export type VoiceState = 'idle' | 'listening' | 'processing' | 'speaking'

const BAR_COUNT = 48

export function VoiceOrb({
  state,
  getLevel,
  getBands,
  size = 320,
  label,
}: {
  state: VoiceState
  getLevel?: () => number
  getBands?: (count: number) => number[]
  size?: number
  label?: string
}) {
  const coreRef = useRef<SVGCircleElement>(null)
  const haloRef = useRef<SVGCircleElement>(null)
  const barsRef = useRef<SVGGElement>(null)
  const stateRef = useRef(state)
  stateRef.current = state

  const levelFn = useRef(getLevel)
  const bandsFn = useRef(getBands)
  levelFn.current = getLevel
  bandsFn.current = getBands

  useEffect(() => {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    let frame = 0
    let smoothed = 0
    const bars = barsRef.current ? Array.from(barsRef.current.children) as SVGLineElement[] : []

    const tick = () => {
      const current = stateRef.current
      const live = current === 'listening' || current === 'speaking'
      const level = live && levelFn.current ? levelFn.current() : 0
      smoothed = smoothed * 0.75 + level * 0.25
      const scale = reduced ? 1 : 1 + smoothed * 0.16

      if (coreRef.current) coreRef.current.setAttribute('r', String(78 * scale))
      if (haloRef.current) {
        haloRef.current.setAttribute('r', String(104 + smoothed * 34))
        haloRef.current.setAttribute('opacity', String(live ? 0.22 + smoothed * 0.5 : 0.18))
      }

      const bands =
        current === 'listening' && bandsFn.current
          ? bandsFn.current(BAR_COUNT / 2)
          : null
      bars.forEach((bar, index) => {
        let value = 0
        if (bands) {
          // Mirror so the ring is symmetric left/right.
          const half = BAR_COUNT / 2
          const b = index < half ? index : BAR_COUNT - 1 - index
          value = bands[b] ?? 0
        } else if (current === 'speaking') {
          value = smoothed * (0.5 + 0.5 * Math.abs(Math.sin(index * 1.7)))
        }
        const inner = 118
        const outer = inner + 4 + (reduced ? 0 : value * 34)
        const angle = (index / BAR_COUNT) * Math.PI * 2 - Math.PI / 2
        bar.setAttribute('x1', String(160 + Math.cos(angle) * inner))
        bar.setAttribute('y1', String(160 + Math.sin(angle) * inner))
        bar.setAttribute('x2', String(160 + Math.cos(angle) * outer))
        bar.setAttribute('y2', String(160 + Math.sin(angle) * outer))
      })

      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [])

  return (
    <div
      className={`orb orb--${state}`}
      style={{ width: size, height: size }}
      role="img"
      aria-label={label ?? `Voice assistant is ${state}`}
    >
      <svg viewBox="0 0 320 320" width={size} height={size}>
        <defs>
          <radialGradient id="orb-core" cx="38%" cy="32%" r="75%">
            <stop offset="0%" stopColor="#4f7ff0" />
            <stop offset="55%" stopColor="#2256d6" />
            <stop offset="100%" stopColor="#13294d" />
          </radialGradient>
          <radialGradient id="orb-core-idle" cx="38%" cy="32%" r="75%">
            <stop offset="0%" stopColor="#35598f" />
            <stop offset="60%" stopColor="#1d3a66" />
            <stop offset="100%" stopColor="#0c1f3d" />
          </radialGradient>
          <radialGradient id="orb-halo">
            <stop offset="60%" stopColor="#3a6ce6" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#3a6ce6" stopOpacity="0" />
          </radialGradient>
        </defs>

        <circle cx="160" cy="160" r="150" className="orb__track" />
        <circle ref={haloRef} cx="160" cy="160" r="104" fill="url(#orb-halo)" className="orb__halo" />

        <g ref={barsRef} className="orb__bars">
          {Array.from({ length: BAR_COUNT }, (_, index) => (
            <line key={index} x1="160" y1="42" x2="160" y2="46" />
          ))}
        </g>

        <circle cx="160" cy="160" r="128" className="orb__ring" />
        {state === 'processing' ? (
          <circle cx="160" cy="160" r="128" className="orb__arc" pathLength={100} />
        ) : null}

        <g className="orb__breath">
          <circle
            ref={coreRef}
            cx="160"
            cy="160"
            r="78"
            fill={state === 'idle' ? 'url(#orb-core-idle)' : 'url(#orb-core)'}
          />
          <ellipse cx="140" cy="128" rx="30" ry="16" fill="#fff" opacity="0.12" />
        </g>
      </svg>
    </div>
  )
}
