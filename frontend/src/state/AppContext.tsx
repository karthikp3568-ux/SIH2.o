import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { api, clearSession, readStoredUser, storeSession } from '../api/client'
import type { LanguageOption, User } from '../api/types'
import { translate } from '../i18n/strings'

interface AppState {
  user: User | null
  language: string
  languages: LanguageOption[]
  speechTag: string
  isAuthenticated: boolean
  isAdmin: boolean
  setLanguage: (code: string) => void
  signIn: (email: string, password: string) => Promise<User>
  signOut: () => Promise<void>
  adoptSession: (payload: { user: User; tokens: any }) => void
  t: (key: string) => string
}

const AppContext = createContext<AppState | null>(null)

const LANGUAGE_KEY = 'ln.language'

const FALLBACK_LANGUAGES: LanguageOption[] = [
  { code: 'en', label: 'English', speech_tag: 'en-IN' },
  { code: 'hi', label: 'हिन्दी', speech_tag: 'hi-IN' },
  { code: 'mr', label: 'मराठी', speech_tag: 'mr-IN' },
  { code: 'ta', label: 'தமிழ்', speech_tag: 'ta-IN' },
]

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => readStoredUser())
  const [language, setLanguageState] = useState<string>(
    () => localStorage.getItem(LANGUAGE_KEY) ?? 'en',
  )
  const [languages, setLanguages] = useState<LanguageOption[]>(FALLBACK_LANGUAGES)

  useEffect(() => {
    // Language list comes from the backend so adding one is a server change.
    api
      .languages()
      .then(setLanguages)
      .catch(() => setLanguages(FALLBACK_LANGUAGES))
  }, [])

  useEffect(() => {
    document.documentElement.lang = language
    localStorage.setItem(LANGUAGE_KEY, language)
  }, [language])

  const setLanguage = useCallback((code: string) => setLanguageState(code), [])

  const signIn = useCallback(async (email: string, password: string) => {
    const response = await api.login(email, password)
    storeSession(response)
    setUser(response.user)
    if (response.user.preferred_language) setLanguageState(response.user.preferred_language)
    return response.user
  }, [])

  const signOut = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      // Signing out locally must succeed even if the network call does not.
    }
    clearSession()
    setUser(null)
  }, [])

  const adoptSession = useCallback((payload: { user: User; tokens: any }) => {
    storeSession(payload)
    setUser(payload.user)
  }, [])

  const speechTag = useMemo(
    () => languages.find((l) => l.code === language)?.speech_tag ?? 'en-IN',
    [languages, language],
  )

  const value = useMemo<AppState>(
    () => ({
      user,
      language,
      languages,
      speechTag,
      isAuthenticated: user !== null,
      isAdmin: user?.role === 'admin' || user?.role === 'counsellor',
      setLanguage,
      signIn,
      signOut,
      adoptSession,
      t: (key: string) => translate(language, key),
    }),
    [user, language, languages, speechTag, setLanguage, signIn, signOut, adoptSession],
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp(): AppState {
  const context = useContext(AppContext)
  if (!context) throw new Error('useApp must be used inside AppProvider')
  return context
}
