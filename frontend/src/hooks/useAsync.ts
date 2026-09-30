import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '../api/client'

export interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
  reload: () => void
  setData: (value: T | null) => void
}

/** Run an async loader on mount and whenever `deps` change. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    loader()
      .then((result) => {
        if (!cancelled && mounted.current) setData(result)
      })
      .catch((caught: unknown) => {
        if (cancelled || !mounted.current) return
        setError(caught instanceof ApiError ? caught.message : 'Something went wrong.')
      })
      .finally(() => {
        if (!cancelled && mounted.current) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { data, loading, error, reload, setData }
}

/** Wrap a mutating call with pending/error state for buttons and forms. */
export function useAction<Args extends unknown[], R>(
  action: (...args: Args) => Promise<R>,
): {
  run: (...args: Args) => Promise<R | undefined>
  pending: boolean
  error: string | null
  clearError: () => void
} {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(
    async (...args: Args) => {
      setPending(true)
      setError(null)
      try {
        return await action(...args)
      } catch (caught) {
        const message =
          caught instanceof ApiError
            ? [caught.message, ...caught.problems.map((p) => `${p.field}: ${p.message}`)].join(' ')
            : 'Something went wrong.'
        setError(message)
        return undefined
      } finally {
        setPending(false)
      }
    },
    [action],
  )

  return { run, pending, error, clearError: () => setError(null) }
}
