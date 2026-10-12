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

/**
 * A sentence a person can act on. Validation problems already read as
 * sentences ("Password must contain an uppercase letter"), so they are shown
 * on their own, without the framework's "Value error," prefix or field codes.
 */
export function friendlyError(caught: unknown): string {
  if (!(caught instanceof ApiError)) return 'Something went wrong. Please try again.'
  if (caught.status === 0) return 'We could not reach the server. Check your connection and try again.'
  if (caught.problems.length > 0) {
    return caught.problems
      .map((p) => p.message.replace(/^Value error,\s*/i, '').replace(/^\w/, (c) => c.toUpperCase()))
      .map((m) => (/[.!?]$/.test(m) ? m : `${m}.`))
      .join(' ')
  }
  return caught.message
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
        setError(friendlyError(caught))
        return undefined
      } finally {
        setPending(false)
      }
    },
    [action],
  )

  return { run, pending, error, clearError: () => setError(null) }
}
