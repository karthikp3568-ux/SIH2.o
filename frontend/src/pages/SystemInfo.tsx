/**
 * Transparency page.
 *
 * A judge, a beneficiary or an auditor can see exactly which integrations are
 * live, which are interface-only, and where the data comes from. This page is
 * the antidote to the usual hackathon ambiguity.
 */

import { Layout } from '../components/Layout'
import { Card, Chip, ErrorState, Loading, Notice } from '../components/ui'
import { useAsync } from '../hooks/useAsync'
import { api } from '../api/client'

const KIND_LABEL: Record<string, string> = {
  speech: 'Speech recognition',
  messaging: 'Messaging channels',
  embedding: 'Embeddings (semantic retrieval)',
  llm: 'Language model',
  data: 'Data sources',
}

export function SystemInfo() {
  const status = useAsync(() => api.status(), [])
  const demo = useAsync(() => api.demoStatus().catch(() => null), [])
  const ranking = useAsync(() => api.rankingConfig(), [])

  if (status.loading) {
    return (
      <Layout>
        <Loading />
      </Layout>
    )
  }
  if (status.error || !status.data) {
    return (
      <Layout>
        <ErrorState message={status.error ?? 'Could not load system status.'} onRetry={status.reload} />
      </Layout>
    )
  }

  const data = status.data

  return (
    <Layout>
      <div className="stack">
        <div>
          <h1>System and data sources</h1>
          <p className="muted">
            What is genuinely wired up, and what is an interface waiting for credentials.
          </p>
        </div>

        <Card>
          <div className="row row--between">
            <div>
              <strong>{data.app_name}</strong>
              <p className="small muted" style={{ margin: 0 }}>
                Version {data.version} · {data.environment} · {data.database}
              </p>
            </div>
            {data.demo_mode ? <Chip tone="warn" icon="▶">Demo mode</Chip> : null}
          </div>
        </Card>

        {Object.entries(data.providers).map(([kind, providers]) => (
          <Card key={kind}>
            <h3>{KIND_LABEL[kind] ?? kind}</h3>
            <div className="stack-sm">
              {providers.map((provider) => (
                <div
                  key={provider.name}
                  className="row row--between"
                  style={{
                    padding: 'var(--space-3)',
                    background: 'var(--grey-050)',
                    borderRadius: 'var(--radius)',
                    alignItems: 'flex-start',
                  }}
                >
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="row" style={{ gap: 'var(--space-2)' }}>
                      <strong>{provider.name}</strong>
                      {provider.is_offline_default ? <Chip icon="⚙">works offline</Chip> : null}
                    </div>
                    <p className="small muted" style={{ margin: '4px 0 0' }}>
                      {provider.detail}
                    </p>
                  </div>
                  <Chip tone={provider.configured ? 'good' : 'warn'} icon={provider.configured ? '✓' : '○'}>
                    {provider.configured ? 'Active' : 'Not configured'}
                  </Chip>
                </div>
              ))}
            </div>
          </Card>
        ))}

        <Card>
          <h3>Capabilities</h3>
          <ul className="tag-list">
            {Object.entries(data.capabilities).map(([key, value]) => (
              <li key={key}>
                <Chip tone={value ? 'good' : 'neutral'} icon={value ? '✓' : '✕'}>
                  {key.replace(/_/g, ' ')}
                </Chip>
              </li>
            ))}
          </ul>
        </Card>

        {ranking.data ? (
          <Card>
            <h3>How recommendations are ordered</h3>
            <Notice tone="warn">
              <p className="small" style={{ margin: 0 }}>
                {String(ranking.data.note)}
              </p>
            </Notice>
            <div className="table-wrap" style={{ marginTop: 'var(--space-4)' }}>
              <table>
                <thead>
                  <tr>
                    <th>Factor</th>
                    <th>Weight</th>
                    <th>Share</th>
                  </tr>
                </thead>
                <tbody>
                  {(ranking.data.weights as { code: string; label: string; weight: number; share: number }[]).map(
                    (weight) => (
                      <tr key={weight.code}>
                        <td>{weight.label}</td>
                        <td>{weight.weight}</td>
                        <td>{Math.round(weight.share * 100)}%</td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
            <p className="small muted" style={{ marginTop: 'var(--space-4)' }}>
              Travel radius by mobility band:{' '}
              {Object.entries(ranking.data.mobility_radius_km as Record<string, number>)
                .map(([band, km]) => `${band} ${km} km`)
                .join(' · ')}
            </p>
          </Card>
        ) : null}

        {demo.data ? (
          <Card>
            <h3>Known limitations</h3>
            <ul className="reason-list">
              {(demo.data.honest_limitations as string[]).map((line, index) => (
                <li key={index}>
                  <span className="reason-list__icon" aria-hidden="true">
                    •
                  </span>
                  <span className="small">{line}</span>
                </li>
              ))}
            </ul>
          </Card>
        ) : null}
      </div>
    </Layout>
  )
}
