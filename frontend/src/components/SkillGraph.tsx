/**
 * The skill graph.
 *
 * The person sits at the centre. Skills they told us about form the inner ring;
 * skills that partly carry over form the outer ring, each placed next to the
 * skill it comes from so the derivation is visible without reading. Competencies
 * still needed for a chosen qualification sit on the same outer ring in a
 * dashed amber state, bridged from the closest thing the person already has.
 *
 * Layout is deterministic (no physics), so the same profile always draws the
 * same picture — important when a judge watches it twice.
 *
 * On narrow screens the SVG would shrink below readable size, so the same data
 * is shown as a layered list instead.
 */

import { useMemo, useState } from 'react'

import type { CompetencyCoverage, SkillGapReport, SkillGraph as SkillGraphData, SkillGraphNode } from '../api/types'
import { confidenceWord, possessive, sourceWord } from '../lib/labels'
import { Icon } from './Icon'
import { Chip, VerificationChip } from './ui'

type Kind = 'direct' | 'category' | 'derived' | 'missing' | 'partial'

interface PlacedNode {
  id: string
  label: string
  kind: Kind
  x: number
  y: number
  w: number
  h: number
  lines: string[]
  node?: SkillGraphNode
  competency?: CompetencyCoverage
  order: number
}

interface PlacedEdge {
  id: string
  from: string
  to: string
  kind: 'spoke' | 'part_of' | 'transfers' | 'bridge'
  d: string
}

const VIEW_W = 860
const VIEW_H = 580
const CX = VIEW_W / 2
const CY = VIEW_H / 2
const INNER = { rx: 172, ry: 118 }
const OUTER = { rx: 340, ry: 228 }
const MAX_DERIVED = 8
const MAX_DEVELOP = 4

function wrap(text: string, max = 20, maxLines = 2): string[] {
  const words = text.split(/\s+/)
  const lines: string[] = []
  let current = ''
  for (const word of words) {
    if ((current + ' ' + word).trim().length > max && current) {
      lines.push(current)
      current = word
    } else {
      current = (current + ' ' + word).trim()
    }
  }
  if (current) lines.push(current)
  if (lines.length > maxLines) return [...lines.slice(0, maxLines - 1), `${lines[maxLines - 1]}…`]
  return lines
}

function circularMean(angles: number[]): number | null {
  if (angles.length === 0) return null
  const x = angles.reduce((sum, a) => sum + Math.cos(a), 0)
  const y = angles.reduce((sum, a) => sum + Math.sin(a), 0)
  return Math.atan2(y, x)
}

function curve(x1: number, y1: number, x2: number, y2: number): string {
  // A gentle bow toward the centre reads as "grows from", not as wiring.
  const mx = (x1 + x2) / 2
  const my = (y1 + y2) / 2
  const qx = mx + (CX - mx) * 0.18
  const qy = my + (CY - my) * 0.18
  return `M${x1.toFixed(1)},${y1.toFixed(1)} Q${qx.toFixed(1)},${qy.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}`
}

function developList(target: SkillGapReport | null | undefined): CompetencyCoverage[] {
  if (!target) return []
  const all = [...target.missing, ...target.partial]
  const order = target.priority_order ?? []
  all.sort((a, b) => {
    const ia = order.indexOf(a.code)
    const ib = order.indexOf(b.code)
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)
  })
  return all.slice(0, MAX_DEVELOP)
}

function useLayout(graph: SkillGraphData, target: SkillGapReport | null | undefined) {
  return useMemo(() => {
    const direct = graph.nodes.filter((n) => n.is_direct && !n.is_category)
    const categories = graph.nodes.filter((n) => n.is_category)
    const derived = graph.nodes
      .filter((n) => !n.is_direct && !n.is_category)
      .sort((a, b) => b.score - a.score)
      .slice(0, MAX_DERIVED)
    const develop = developList(target)

    // Outer ring: derived skills grouped by the skill they come from, then the
    // competencies to develop as their own group.
    const directCodes = direct.map((d) => d.code)
    const outerOrder: { id: string; kind: Kind; node?: SkillGraphNode; competency?: CompetencyCoverage }[] = []
    for (const code of directCodes) {
      for (const node of derived.filter((n) => n.derived_from === code)) outerOrder.push({ id: node.code, kind: 'derived', node })
    }
    for (const node of derived.filter((n) => !directCodes.includes(n.derived_from ?? ''))) {
      outerOrder.push({ id: node.code, kind: 'derived', node })
    }
    for (const competency of develop) {
      outerOrder.push({
        id: `need:${competency.code}`,
        kind: competency.band === 'partial' ? 'partial' : 'missing',
        competency,
      })
    }

    const outerAngles = new Map<string, number>()
    const count = Math.max(outerOrder.length, 1)
    // Rotate so the "to develop" group lands lower right, away from the title.
    const offset = -Math.PI / 2 - (develop.length > 0 ? 0.35 : 0)
    outerOrder.forEach((item, index) => outerAngles.set(item.id, offset + ((index + 0.5) / count) * Math.PI * 2))

    // Inner ring: held skills in the same order as their outer groups, each
    // followed by the areas of work it belongs to. Spacing is even (so nothing
    // overlaps); the ring is then rotated so each held skill faces its group.
    const ownerOf = (category: string) =>
      graph.edges.find((e) => e.target === category && directCodes.includes(e.source))?.source ?? null
    const innerOrder: string[] = []
    for (const node of direct) {
      innerOrder.push(node.code)
      for (const category of categories) if (ownerOf(category.code) === node.code) innerOrder.push(category.code)
    }
    for (const category of categories) if (!innerOrder.includes(category.code)) innerOrder.push(category.code)

    const step = (Math.PI * 2) / Math.max(innerOrder.length, 1)
    const deltas: number[] = []
    direct.forEach((node) => {
      const children = derived.filter((d) => d.derived_from === node.code).map((d) => outerAngles.get(d.code)!)
      const desired = circularMean(children)
      if (desired !== null) deltas.push(desired - innerOrder.indexOf(node.code) * step)
    })
    const rotation = circularMean(deltas) ?? -Math.PI / 2
    const innerAngles = new Map(innerOrder.map((code, index) => [code, rotation + index * step]))

    const placed: PlacedNode[] = []
    const place = (id: string, label: string, kind: Kind, angle: number, ring: typeof INNER, order: number, extra: Partial<PlacedNode>) => {
      const competency = kind === 'missing' || kind === 'partial'
      const lines = wrap(label, kind === 'direct' || kind === 'category' ? 18 : competency ? 22 : 20, competency ? 3 : 2)
      const longest = Math.max(...lines.map((l) => l.length))
      const w = Math.min(196, Math.max(96, longest * 7.4 + 44))
      const h = 20 + lines.length * 16
      placed.push({
        id,
        label,
        kind,
        x: CX + Math.cos(angle) * ring.rx,
        y: CY + Math.sin(angle) * ring.ry,
        w,
        h,
        lines,
        order,
        ...extra,
      })
    }

    let order = 0
    for (const node of [...direct, ...categories]) {
      place(node.code, node.name, node.is_category ? 'category' : 'direct', innerAngles.get(node.code) ?? 0, INNER, order++, { node })
    }
    for (const item of outerOrder) {
      const label = item.node?.name ?? item.competency?.name ?? item.id
      place(item.id, label, item.kind, outerAngles.get(item.id) ?? 0, OUTER, order++, {
        node: item.node,
        competency: item.competency,
      })
    }

    const byId = new Map(placed.map((p) => [p.id, p]))
    const edges: PlacedEdge[] = []
    for (const node of placed.filter((p) => p.kind === 'direct' || p.kind === 'category')) {
      edges.push({ id: `c-${node.id}`, from: 'centre', to: node.id, kind: 'spoke', d: curve(CX, CY, node.x, node.y) })
    }
    for (const edge of graph.edges) {
      const a = byId.get(edge.source)
      const b = byId.get(edge.target)
      if (!a || !b) continue
      edges.push({
        id: `e-${edge.source}-${edge.target}`,
        from: a.id,
        to: b.id,
        kind: edge.relation === 'part_of' ? 'part_of' : 'transfers',
        d: curve(a.x, a.y, b.x, b.y),
      })
    }
    for (const node of placed.filter((p) => p.competency)) {
      const bridges = [...(node.competency?.contributing_skills ?? [])]
        .sort((a, b) => b.contribution - a.contribution)
        .map((c) => byId.get(c.skill_code))
        .filter((p): p is PlacedNode => Boolean(p))
        .slice(0, 1)
      if (bridges.length === 0) {
        edges.push({ id: `b-centre-${node.id}`, from: 'centre', to: node.id, kind: 'bridge', d: curve(CX, CY, node.x, node.y) })
      }
      for (const source of bridges) {
        edges.push({ id: `b-${source.id}-${node.id}`, from: source.id, to: node.id, kind: 'bridge', d: curve(source.x, source.y, node.x, node.y) })
      }
    }

    return { placed, edges, direct, categories, derived, develop, hiddenDerived: graph.nodes.filter((n) => !n.is_direct && !n.is_category).length - derived.length }
  }, [graph, target])
}

const KIND_META: Record<Kind, { label: string; icon: string }> = {
  direct: { label: 'A skill you have', icon: 'check' },
  category: { label: 'An area of your work', icon: 'layers' },
  derived: { label: 'Partly carries over', icon: 'arrowRight' },
  missing: { label: 'To develop', icon: 'plus' },
  partial: { label: 'Partly there — to strengthen', icon: 'plus' },
}

function NodeDetail({
  node,
  related,
  targetTitle,
}: {
  node: PlacedNode | null
  related: string[]
  targetTitle?: string
}) {
  if (!node) {
    return (
      <div className="graph-detail graph-detail--empty">
        <Icon name="graph" size={28} strokeWidth={1.6} />
        <p>Select any skill to see where it came from and how sure we are about it.</p>
      </div>
    )
  }
  const meta = KIND_META[node.kind]
  return (
    <div className="graph-detail enter" key={node.id}>
      <span className={`graph-detail__kind graph-detail__kind--${node.kind}`}>
        <Icon name={meta.icon} size={13} strokeWidth={2.6} /> {meta.label}
      </span>
      <h3>{node.label}</h3>

      {node.node ? (
        <dl className="graph-detail__facts">
          {node.kind === 'derived' ? (
            <div>
              <dt>Why it’s here</dt>
              <dd>{node.node.derivation ?? 'Related to your work'}</dd>
            </div>
          ) : (
            <div>
              <dt>Source</dt>
              <dd>{sourceWord(node.node.source)}</dd>
            </div>
          )}
          {node.kind === 'direct' ? (
            <>
              <div>
                <dt>Level</dt>
                <dd>
                  {node.node.proficiency ? node.node.proficiency.charAt(0).toUpperCase() + node.node.proficiency.slice(1) : 'Basic'}
                  {node.node.years_experience ? ` · ${node.node.years_experience} years` : ''}
                </dd>
              </div>
              <div>
                <dt>Confidence</dt>
                <dd>{confidenceWord(node.node.confidence)}</dd>
              </div>
            </>
          ) : null}
          <div>
            <dt>Verification</dt>
            <dd>
              {node.kind === 'derived' ? (
                <span className="muted">Not a claim about you — credit only</span>
              ) : (
                <VerificationChip status={node.node.verification_status ?? 'unverified'} />
              )}
            </dd>
          </div>
        </dl>
      ) : null}

      {node.competency ? (
        <dl className="graph-detail__facts">
          <div>
            <dt>Needed for</dt>
            <dd>{targetTitle ?? 'This qualification'}</dd>
          </div>
          {node.competency.nos_code ? (
            <div>
              <dt>Standard</dt>
              <dd>{node.competency.nos_code}</dd>
            </div>
          ) : null}
          <div>
            <dt>Where you stand</dt>
            <dd>{node.competency.explanation}</dd>
          </div>
        </dl>
      ) : null}

      {related.length > 0 ? (
        <div>
          <div className="graph-detail__sub">Connected to</div>
          <ul className="tag-list">
            {related.map((name) => (
              <li key={name}>
                <Chip>{name}</Chip>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

export function SkillGraph({
  graph,
  name,
  target,
}: {
  graph: SkillGraphData
  name: string
  target?: SkillGapReport | null
}) {
  const layout = useLayout(graph, target)
  const [active, setActive] = useState<string | null>(null)
  const [hover, setHover] = useState<string | null>(null)
  const focus = hover ?? active

  const lit = useMemo(() => {
    if (!focus) return null
    const set = new Set<string>([focus])
    for (const edge of layout.edges) {
      if (edge.from === focus || edge.to === focus) {
        set.add(edge.from)
        set.add(edge.to)
      }
    }
    return set
  }, [focus, layout.edges])

  const activeNode = layout.placed.find((p) => p.id === active) ?? null
  const related = activeNode
    ? layout.edges
        .filter((e) => e.from === activeNode.id || e.to === activeNode.id)
        .map((e) => (e.from === activeNode.id ? e.to : e.from))
        .filter((id) => id !== 'centre')
        .map((id) => layout.placed.find((p) => p.id === id)?.label)
        .filter((label): label is string => Boolean(label))
    : []

  if (graph.nodes.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state__art">
          <Icon name="graph" size={36} strokeWidth={1.6} />
        </div>
        <h3>No skills yet</h3>
        <p>Tell us about the work you do, and your skills will appear here.</p>
      </div>
    )
  }

  const firstName = name.split(' ')[0]

  return (
    <div className="skill-graph">
      <div className="skill-graph__canvas">
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          role="group"
          aria-label={`${possessive(firstName)} skill graph`}
          className={lit ? 'is-focused' : ''}
        >
          <ellipse cx={CX} cy={CY} rx={INNER.rx} ry={INNER.ry} className="skill-graph__orbit" />
          <ellipse cx={CX} cy={CY} rx={OUTER.rx} ry={OUTER.ry} className="skill-graph__orbit" />

          <g>
            {layout.edges.map((edge, index) => (
              <path
                key={edge.id}
                d={edge.d}
                pathLength={1}
                className={`sg-edge sg-edge--${edge.kind} ${lit && lit.has(edge.from) && lit.has(edge.to) && (edge.from === focus || edge.to === focus) ? 'is-lit' : ''}`}
                style={{ animationDelay: `${200 + index * 45}ms` }}
              />
            ))}
          </g>

          <g className="sg-centre">
            <circle cx={CX} cy={CY} r={50} />
            <text x={CX} y={CY - 4} className="sg-centre__initial">
              {firstName.charAt(0).toUpperCase()}
            </text>
            <text x={CX} y={CY + 20} className="sg-centre__label">
              {firstName.toUpperCase()}
            </text>
          </g>

          {layout.placed.map((node) => {
            const dim = lit && !lit.has(node.id)
            return (
              <g
                key={node.id}
                className={`sg-node sg-node--${node.kind} ${active === node.id ? 'is-active' : ''} ${dim ? 'is-dim' : ''}`}
                transform={`translate(${node.x.toFixed(1)} ${node.y.toFixed(1)})`}
                tabIndex={0}
                role="button"
                aria-pressed={active === node.id}
                aria-label={`${node.label} — ${KIND_META[node.kind].label}`}
                onClick={() => setActive(active === node.id ? null : node.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    setActive(active === node.id ? null : node.id)
                  }
                }}
                onMouseEnter={() => setHover(node.id)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(node.id)}
                onBlur={() => setHover(null)}
              >
                <g className="sg-node__body" style={{ animationDelay: `${120 + node.order * 70}ms` }}>
                  <rect x={-node.w / 2} y={-node.h / 2} width={node.w} height={node.h} rx={node.h / 2} />
                  <circle cx={-node.w / 2 + 17} cy={0} r={8} className="sg-node__mark" />
                  {node.kind === 'direct' ? (
                    <path d={`M${-node.w / 2 + 13},0 l3,3 l5,-6`} className="sg-node__glyph" />
                  ) : node.kind === 'missing' || node.kind === 'partial' ? (
                    <path d={`M${-node.w / 2 + 17},-4 v8 M${-node.w / 2 + 13},0 h8`} className="sg-node__glyph" />
                  ) : null}
                  {node.lines.map((line, index) => (
                    <text
                      key={index}
                      x={-node.w / 2 + 32}
                      y={(index - (node.lines.length - 1) / 2) * 16 + 4.5}
                      className="sg-node__text"
                    >
                      {line}
                    </text>
                  ))}
                </g>
              </g>
            )
          })}
        </svg>

        <ul className="skill-graph__legend" aria-label="Legend">
          <li>
            <span className="swatch swatch--direct" /> Skills you have
          </li>
          <li>
            <span className="swatch swatch--category" /> Areas of work
          </li>
          <li>
            <span className="swatch swatch--derived" /> Partly carries over
          </li>
          {layout.develop.length > 0 ? (
            <li>
              <span className="swatch swatch--missing" /> To develop
            </li>
          ) : null}
        </ul>
      </div>

      <aside className="skill-graph__side" aria-live="polite">
        <NodeDetail node={activeNode} related={related} targetTitle={target?.qualification_title} />
      </aside>

      {/* Narrow screens: the same graph as layers. */}
      <div className="skill-graph__list">
        <section>
          <h4>
            <span className="swatch swatch--direct" /> Skills you have
          </h4>
          <ul className="tag-list">
            {layout.direct.map((n) => (
              <li key={n.code}>
                <Chip tone="good" icon="check">
                  {n.name}
                  {n.years_experience ? ` · ${n.years_experience} yr` : ''}
                </Chip>
              </li>
            ))}
            {layout.categories.map((n) => (
              <li key={n.code}>
                <Chip icon="layers">{n.name}</Chip>
              </li>
            ))}
          </ul>
        </section>
        {layout.derived.length > 0 ? (
          <section>
            <h4>
              <span className="swatch swatch--derived" /> Partly carries over
            </h4>
            <ul className="skill-graph__rows">
              {layout.derived.map((n) => (
                <li key={n.code}>
                  <strong>{n.name}</strong>
                  <span>{n.derivation}</span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {layout.develop.length > 0 ? (
          <section>
            <h4>
              <span className="swatch swatch--missing" /> To develop
            </h4>
            <ul className="skill-graph__rows">
              {layout.develop.map((c) => (
                <li key={c.code}>
                  <strong>{c.name}</strong>
                  <span>{c.band === 'partial' ? 'Partly there' : 'Not yet covered'}</span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </div>
  )
}
