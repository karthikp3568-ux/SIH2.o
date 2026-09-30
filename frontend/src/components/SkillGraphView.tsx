/**
 * Skill graph rendered as a grouped radial-free layout.
 *
 * A force-directed graph looks impressive and tells a low-literacy user
 * nothing. Instead we show the person at the centre, their directly held
 * skills as the first ring, and derived skills grouped underneath with the
 * derivation stated in words — because "you partly get this from pump repair"
 * is the actual insight.
 */

import type { SkillGraph, SkillGraphNode } from '../api/types'
import { Chip, Meter } from './ui'

function proficiencyLabel(node: SkillGraphNode): string {
  if (!node.is_direct) return node.derivation ?? 'related to your work'
  const level = node.proficiency ?? 'basic'
  const years = node.years_experience ? ` · ${node.years_experience} yr` : ''
  return `${level}${years}`
}

export function SkillGraphView({ graph, name }: { graph: SkillGraph; name: string }) {
  const direct = graph.nodes.filter((n) => n.is_direct && !n.is_category)
  const categories = graph.nodes.filter((n) => n.is_category)
  const derived = graph.nodes.filter((n) => !n.is_direct && !n.is_category)

  if (graph.nodes.length === 0) {
    return (
      <p className="muted">
        No skills recorded yet. Tell us about the work you do and they will appear here.
      </p>
    )
  }

  return (
    <div className="stack">
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-3)',
          padding: 'var(--space-3)',
          background: 'var(--navy-800)',
          color: '#fff',
          borderRadius: 'var(--radius)',
        }}
      >
        <span style={{ fontSize: '1.6rem' }} aria-hidden="true">
          👤
        </span>
        <div>
          <strong>{name}</strong>
          <div className="tiny" style={{ opacity: 0.85 }}>
            {direct.length} skill{direct.length === 1 ? '' : 's'} you told us about
            {categories.length ? ` · ${categories.length} area${categories.length === 1 ? '' : 's'} of work` : ''}
          </div>
        </div>
      </div>

      <section>
        <h4>What you can do now</h4>
        <div className="grid grid--2">
          {direct.map((node) => (
            <div key={node.code} className="card card--quiet" style={{ padding: 'var(--space-3)' }}>
              <div className="row row--between" style={{ marginBottom: 6 }}>
                <strong>{node.name}</strong>
                <Chip tone="good" icon="●">
                  yours
                </Chip>
              </div>
              <Meter value={node.score} tone="good" />
              <div className="tiny muted" style={{ marginTop: 6 }}>
                {proficiencyLabel(node)}
              </div>
            </div>
          ))}
        </div>
      </section>

      {derived.length > 0 ? (
        <section>
          <h4>What partly carries over</h4>
          <p className="small muted">
            These are not claims about you. They are the credit your existing skills give you
            towards related work, and they are why some pathways are shorter for you than for
            someone starting fresh.
          </p>
          <div className="grid grid--2">
            {derived.slice(0, 8).map((node) => (
              <div key={node.code} className="card card--quiet" style={{ padding: 'var(--space-3)' }}>
                <div className="row row--between" style={{ marginBottom: 6 }}>
                  <strong>{node.name}</strong>
                  <Chip tone="info" icon="↝">
                    partial
                  </Chip>
                </div>
                <Meter value={node.score} />
                <div className="tiny muted" style={{ marginTop: 6 }}>
                  {node.derivation ?? 'related to your work'}
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {categories.length > 0 ? (
        <section>
          <h4>Your areas of work</h4>
          <ul className="tag-list">
            {categories.map((node) => (
              <li key={node.code}>
                <Chip icon="▣">{node.name}</Chip>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
