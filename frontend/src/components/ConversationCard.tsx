/**
 * One turn of the conversation, drawn as a card rather than a chat bubble.
 *
 * A beneficiary turn can carry what the system extracted from it; those facts
 * appear one after another so the person can watch themselves being understood.
 */

import { Icon } from './Icon'

export interface Turn {
  id: string
  /** The stored message id, for a beneficiary turn the server has kept. */
  serverId?: string | null
  role: 'assistant' | 'beneficiary'
  text: string
  /** Facts newly understood from this turn, in plain words. */
  extracted?: string[]
  heardConfidence?: number | null
  language?: string | null
}

export function ConversationCard({ turn, animate = false }: { turn: Turn; animate?: boolean }) {
  const isUser = turn.role === 'beneficiary'
  return (
    <article className={`convo-card convo-card--${turn.role} ${animate ? 'enter' : ''}`}>
      <div className="convo-card__who">
        <span className="convo-card__avatar" aria-hidden="true">
          <Icon name={isUser ? 'user' : 'compass'} size={14} strokeWidth={2.4} />
        </span>
        {isUser ? 'You said' : 'Navigator asked'}
        {isUser && typeof turn.heardConfidence === 'number' ? (
          <span className="convo-card__meta">
            <Icon name="mic" size={12} /> heard {Math.round(turn.heardConfidence * 100)}%
          </span>
        ) : null}
      </div>
      <p className="convo-card__text">{isUser ? `“${turn.text}”` : turn.text}</p>
      {turn.extracted && turn.extracted.length > 0 ? (
        <ul className="extract-list" aria-label="What we understood from this">
          {turn.extracted.map((fact, index) => (
            <li
              key={fact}
              className={animate ? 'pop' : ''}
              style={animate ? { animationDelay: `${250 + index * 220}ms` } : undefined}
            >
              <Icon name="plus" size={13} strokeWidth={3} />
              {fact}
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  )
}
