/**
 * Proximity map.
 *
 * Not a GIS view: a local, to-scale sketch centred on the beneficiary, drawn
 * from real coordinates with an equirectangular projection (accurate to well
 * under 1% at these distances). It needs no tile server, so it works offline
 * and in low-bandwidth settings. Its single job is to make "near" visible.
 */

import { useMemo, useState } from 'react'

import { Icon, OPPORTUNITY_TYPE } from './Icon'
import { TrustBadge } from './ui'

export interface MapPoint {
  id: string
  title: string
  provider: string
  type: string
  latitude: number
  longitude: number
  distanceKm: number | null
  /** Rank when this point is one of the recommendations. */
  rank?: number
  available: boolean
  verificationStatus: string
  lastVerifiedAt: string | null
  validUntil?: string | null
}

const SIZE = 420
const C = SIZE / 2
const PAD = 26

const TYPE_TONE: Record<string, string> = {
  training: 'training',
  apprenticeship: 'training',
  job: 'job',
  enterprise: 'enterprise',
  self_employment: 'enterprise',
}

function niceRings(extent: number): number[] {
  const candidates = [2, 5, 10, 15, 25, 50, 100, 150, 250]
  return candidates.filter((r) => r < extent * 0.98).slice(-3)
}

export function MapPanel({
  origin,
  points,
  radiusKm,
  highlight,
  onHighlight,
}: {
  origin: { latitude: number; longitude: number; label: string }
  points: MapPoint[]
  radiusKm: number | null
  highlight?: string | null
  onHighlight?: (id: string | null) => void
}) {
  const [selected, setSelected] = useState<string | null>(null)

  const layout = useMemo(() => {
    const cos = Math.cos((origin.latitude * Math.PI) / 180)
    const project = (p: { latitude: number; longitude: number }) => ({
      kx: (p.longitude - origin.longitude) * 111.32 * cos,
      ky: (p.latitude - origin.latitude) * 110.57,
    })
    const ranked = points.filter((p) => p.rank)
    const farthestRanked = Math.max(0, ...ranked.map((p) => p.distanceKm ?? 0))
    // Frame the pathways first; only stretch to show the travel limit when it
    // is close enough not to shrink everything else into the centre.
    let extent = Math.max(farthestRanked * 1.3, 10)
    if (radiusKm && radiusKm < extent * 1.8) extent = Math.max(extent, radiusKm * 1.1)
    const scale = (C - PAD) / extent
    const placed = points
      .map((p) => {
        const { kx, ky } = project(p)
        return { ...p, x: C + kx * scale, y: C - ky * scale, km: Math.hypot(kx, ky) }
      })
      .filter((p) => p.km <= extent)
    const hidden = points.length - placed.length
    return { placed, hidden, scale, extent, rings: niceRings(extent) }
  }, [origin, points, radiusKm])

  const active = layout.placed.find((p) => p.id === (selected ?? highlight)) ?? null
  const ordered = [...layout.placed].sort((a, b) => (a.rank ? 1 : 0) - (b.rank ? 1 : 0))

  return (
    <div className="map-panel">
      <div className="map-panel__head">
        <div>
          <span className="eyebrow">
            <Icon name="map" size={13} /> Near you
          </span>
          <div className="map-panel__place">{origin.label}</div>
        </div>
        {radiusKm ? <span className="map-panel__radius">Within {Math.round(radiusKm)} km</span> : null}
      </div>

      <div className="map-panel__stage">
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={`Map of opportunities around ${origin.label}`}>
          <defs>
            <radialGradient id="map-ground">
              <stop offset="0%" stopColor="#eef6f2" />
              <stop offset="100%" stopColor="#f6f4ef" />
            </radialGradient>
            <pattern id="map-grid" width="28" height="28" patternUnits="userSpaceOnUse">
              <path d="M28 0H0V28" fill="none" stroke="#e4e0d7" strokeWidth="0.8" />
            </pattern>
          </defs>
          <rect width={SIZE} height={SIZE} rx="18" fill="url(#map-ground)" />
          <rect width={SIZE} height={SIZE} rx="18" fill="url(#map-grid)" opacity="0.7" />

          {layout.rings.map((km) => (
            <g key={km} className="map-ring">
              <circle cx={C} cy={C} r={km * layout.scale} />
              <text x={C + km * layout.scale * 0.707 + 4} y={C - km * layout.scale * 0.707 - 4}>
                {km} km
              </text>
            </g>
          ))}
          {radiusKm && radiusKm <= layout.extent ? (
            <circle cx={C} cy={C} r={radiusKm * layout.scale} className="map-limit" />
          ) : null}

          <g className="map-compass" transform={`translate(${SIZE - 30} 30)`}>
            <circle r="13" />
            <path d="M0,-8 L4,4 L0,1 L-4,4 Z" />
            <text y="-17">N</text>
          </g>

          {ordered.map((p) => {
            const tone = TYPE_TONE[p.type] ?? 'job'
            const isActive = active?.id === p.id
            return (
              <g
                key={p.id}
                className={`map-pin map-pin--${tone} ${p.rank ? 'map-pin--ranked' : ''} ${isActive ? 'is-active' : ''} ${!p.available ? 'is-closed' : ''}`}
                transform={`translate(${p.x.toFixed(1)} ${p.y.toFixed(1)})`}
                tabIndex={0}
                role="button"
                aria-label={`${p.title}, ${p.distanceKm !== null ? `${Math.round(p.distanceKm)} km` : 'distance unknown'}`}
                onClick={() => setSelected(selected === p.id ? null : p.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    setSelected(selected === p.id ? null : p.id)
                  }
                }}
                onMouseEnter={() => onHighlight?.(p.id)}
                onMouseLeave={() => onHighlight?.(null)}
              >
                {p.rank ? (
                  <>
                    <circle r="17" className="map-pin__halo" />
                    <circle r="12" className="map-pin__dot" />
                    <text y="4.5" className="map-pin__num">
                      {p.rank}
                    </text>
                  </>
                ) : (
                  <circle r="5.5" className="map-pin__dot" />
                )}
              </g>
            )
          })}

          <g className="map-you" transform={`translate(${C} ${C})`}>
            <circle r="20" className="map-you__pulse" />
            <circle r="9" className="map-you__dot" />
            <text y="30">You</text>
          </g>
        </svg>

        {active ? (
          <div
            className="map-pop enter"
            style={{
              left: `${Math.min(70, Math.max(30, (active.x / SIZE) * 100))}%`,
              top: `${(active.y / SIZE) * 100}%`,
              transform: active.y > SIZE * 0.55 ? 'translate(-50%, calc(-100% - 22px))' : 'translate(-50%, 22px)',
            }}
            role="status"
          >
            <div className="map-pop__type">
              <Icon name={OPPORTUNITY_TYPE[active.type]?.icon ?? 'briefcase'} size={13} />
              {OPPORTUNITY_TYPE[active.type]?.label ?? active.type}
              {active.distanceKm !== null ? ` · ${active.distanceKm < 1 ? 'here' : `${Math.round(active.distanceKm)} km`}` : ''}
            </div>
            <strong>{active.title}</strong>
            <div className="map-pop__provider">{active.provider}</div>
            <div className="map-pop__row">
              <span className={active.available ? 'is-ok' : 'is-warn'}>
                <Icon name={active.available ? 'checkCircle' : 'xCircle'} size={13} /> {active.available ? 'Open now' : 'Closed'}
              </span>
              <TrustBadge verificationStatus={active.verificationStatus} lastVerifiedAt={active.lastVerifiedAt} validUntil={active.validUntil} compact />
            </div>
          </div>
        ) : null}
      </div>

      <ul className="map-legend">
        <li>
          <span className="map-legend__dot map-legend__dot--ranked">1</span> Your pathways
        </li>
        <li>
          <span className="map-legend__dot map-pin--training" /> Training
        </li>
        <li>
          <span className="map-legend__dot map-pin--job" /> Jobs
        </li>
        <li>
          <span className="map-legend__dot map-pin--enterprise" /> Enterprise
        </li>
        {radiusKm && radiusKm <= layout.extent ? (
          <li>
            <span className="map-legend__limit" /> Your travel limit
          </li>
        ) : null}
      </ul>
      {layout.hidden > 0 ? (
        <p className="tiny muted" style={{ margin: '6px 0 0' }}>
          {layout.hidden} more listing{layout.hidden === 1 ? ' is' : 's are'} further away than shown.
        </p>
      ) : null}
    </div>
  )
}
