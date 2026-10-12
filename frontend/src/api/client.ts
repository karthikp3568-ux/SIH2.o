/**
 * Typed API client.
 *
 * The access token lives in memory plus sessionStorage (not localStorage) so it
 * does not survive the browser session. No API key of any kind is shipped to
 * the browser - every third-party credential stays server side.
 */

import type {
  Analytics,
  AuditEntry,
  AuthResponse,
  BeneficiaryProfile,
  Conversation,
  ConversationStart,
  DemoSession,
  Explanation,
  LanguageOption,
  MessageResponse,
  Opportunity,
  Outcome,
  RecommendationRun,
  SkillGapReport,
  SkillGraph,
  Slot,
  SystemStatus,
  TokenPair,
  User,
} from './types'

const TOKEN_KEY = 'ln.tokens'
const USER_KEY = 'ln.user'

export class ApiError extends Error {
  status: number
  problems: { field: string; message: string }[]

  constructor(status: number, message: string, problems: { field: string; message: string }[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.problems = problems
  }
}

function readTokens(): TokenPair | null {
  try {
    const raw = sessionStorage.getItem(TOKEN_KEY)
    return raw ? (JSON.parse(raw) as TokenPair) : null
  } catch {
    return null
  }
}

export function storeSession(auth: { user: User; tokens: TokenPair }): void {
  sessionStorage.setItem(TOKEN_KEY, JSON.stringify(auth.tokens))
  sessionStorage.setItem(USER_KEY, JSON.stringify(auth.user))
}

export function readStoredUser(): User | null {
  try {
    const raw = sessionStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as User) : null
  } catch {
    return null
  }
}

export function clearSession(): void {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(USER_KEY)
}

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api'

let refreshing: Promise<boolean> | null = null

async function refreshTokens(): Promise<boolean> {
  const tokens = readTokens()
  if (!tokens?.refresh_token) return false
  try {
    const response = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: tokens.refresh_token }),
    })
    if (!response.ok) return false
    const fresh = (await response.json()) as TokenPair
    sessionStorage.setItem(TOKEN_KEY, JSON.stringify(fresh))
    return true
  } catch {
    return false
  }
}

interface RequestOptions {
  method?: string
  body?: unknown
  formData?: FormData
  signal?: AbortSignal
  /** Set false for endpoints that must work signed out. */
  auth?: boolean
  retryOnUnauthorised?: boolean
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, formData, signal, auth = true, retryOnUnauthorised = true } = options

  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth) {
    const tokens = readTokens()
    if (tokens?.access_token) headers.Authorization = `Bearer ${tokens.access_token}`
  }

  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal,
    })
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error
    throw new ApiError(0, 'Could not reach the server. Check your connection and try again.')
  }

  // One transparent refresh attempt, then give up and surface the 401.
  if (response.status === 401 && auth && retryOnUnauthorised) {
    refreshing = refreshing ?? refreshTokens()
    const refreshed = await refreshing
    refreshing = null
    if (refreshed) {
      return request<T>(path, { ...options, retryOnUnauthorised: false })
    }
    clearSession()
  }

  if (response.status === 204) return undefined as T

  const text = await response.text()
  const payload = text ? safeJson(text) : null

  if (!response.ok) {
    const detail =
      (payload && typeof payload === 'object' && 'detail' in payload
        ? String((payload as { detail: unknown }).detail)
        : null) ?? `Request failed (${response.status})`
    const problems =
      payload && typeof payload === 'object' && 'problems' in payload
        ? ((payload as { problems: { field: string; message: string }[] }).problems ?? [])
        : []
    throw new ApiError(response.status, detail, problems)
  }

  return payload as T
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const api = {
  // --- system ---
  status: () => request<SystemStatus>('/system/status', { auth: false }),
  languages: () => request<LanguageOption[]>('/system/languages', { auth: false }),
  slots: (language: string) => request<Slot[]>(`/system/slots?language=${language}`, { auth: false }),
  rankingConfig: () => request<Record<string, any>>('/system/ranking-config', { auth: false }),

  // --- auth ---
  login: (email: string, password: string) =>
    request<AuthResponse>('/auth/login', { method: 'POST', body: { email, password }, auth: false }),
  register: (payload: Record<string, unknown>) =>
    request<AuthResponse>('/auth/register', { method: 'POST', body: payload, auth: false }),
  sendOtp: (payload: { destination: string; challenge_type: 'email' | 'phone' | 'password_reset' }) =>
    request<import('./types').SendOtpResponse>('/auth/otp/send', { method: 'POST', body: payload, auth: false }),
  verifyOtp: (payload: { destination: string; challenge_type: 'email' | 'phone' | 'password_reset'; code: string }) =>
    request<import('./types').VerifyOtpResponse>('/auth/otp/verify', { method: 'POST', body: payload, auth: false }),
  requestPasswordReset: (destination: string) =>
    request<import('./types').SendOtpResponse>('/auth/password-reset/request', {
      method: 'POST',
      body: { destination, challenge_type: 'password_reset' },
      auth: false,
    }),
  confirmPasswordReset: (payload: { email: string; code: string; new_password: string }) =>
    request<{ message: string }>('/auth/password-reset/confirm', { method: 'POST', body: payload, auth: false }),
  me: () => request<User>('/auth/me'),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),

  // --- demo ---
  demoReset: () => request<DemoSession>('/demo/ravi/reset', { method: 'POST', auth: false }),
  demoScript: () => request<Record<string, any>>('/demo/script', { auth: false }),
  demoStatus: () => request<Record<string, any>>('/demo/status', { auth: false }),

  // --- conversation ---
  startConversation: (payload: { language?: string; channel?: string; resume?: boolean }) =>
    request<ConversationStart>('/conversation/start', { method: 'POST', body: payload }),
  getConversation: (id: string) => request<Conversation>(`/conversation/${id}`),
  sendMessage: (
    id: string,
    payload: {
      text: string
      language?: string
      asr_confidence?: number
      speech_provider?: string
      slot_answer?: string
      /** One id per utterance: a duplicate send returns the first result. */
      client_message_id?: string
      /** A low-confidence message the person has now confirmed. */
      confirm_message_id?: string
    },
  ) => request<MessageResponse>(`/conversation/${id}/message`, { method: 'POST', body: payload }),
  confirmConversation: (id: string, payload: Record<string, unknown>) =>
    request<{ profile: BeneficiaryProfile; recommendations_generated: boolean; recommendation_run_id: string | null }>(
      `/conversation/${id}/confirm`,
      { method: 'POST', body: payload },
    ),

  // --- profile ---
  profile: () => request<BeneficiaryProfile>('/beneficiary/profile'),
  profileById: (id: string) => request<BeneficiaryProfile>(`/beneficiary/${id}/profile`),
  patchProfile: (payload: Record<string, unknown>) =>
    request<BeneficiaryProfile>('/beneficiary/profile', { method: 'PATCH', body: payload }),
  setLocation: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>('/beneficiary/location', { method: 'PUT', body: payload }),
  addSkill: (payload: { label: string; proficiency?: string; years_experience?: number }) =>
    request<Record<string, unknown>>('/beneficiary/skills', { method: 'POST', body: payload }),
  removeSkill: (id: string) => request<void>(`/beneficiary/skills/${id}`, { method: 'DELETE' }),
  skillGraph: (beneficiaryId: string) => request<SkillGraph>(`/skill-graph/${beneficiaryId}`),
  skillGap: (payload: { qualification_id?: string; limit?: number }) =>
    request<{ beneficiary_id: string; skill_graph: SkillGraph; reports: SkillGapReport[] }>(
      '/skill-gap/analyze',
      { method: 'POST', body: payload },
    ),

  // --- recommendations ---
  generate: (payload: Record<string, unknown> = {}) =>
    request<RecommendationRun>('/recommendations/generate', { method: 'POST', body: payload }),
  latestRun: (beneficiaryId: string) => request<RecommendationRun>(`/recommendations/${beneficiaryId}`),
  explanation: (recommendationId: string) =>
    request<Explanation>(`/recommendations/detail/${recommendationId}/explanation`),
  exclusions: (beneficiaryId: string) =>
    request<Record<string, any>>(`/recommendations/${beneficiaryId}/exclusions`),
  selectPathway: (pathwayId: string, note?: string) =>
    request<Outcome>(`/pathways/${pathwayId}/select`, { method: 'POST', body: { note } }),

  // --- outcomes ---
  outcomes: () => request<Outcome[]>('/outcomes'),
  outcomesFor: (beneficiaryId: string) => request<Outcome[]>(`/outcomes/beneficiary/${beneficiaryId}`),
  updateOutcome: (id: string, payload: Record<string, unknown>) =>
    request<Outcome>(`/outcomes/${id}`, { method: 'PATCH', body: payload }),
  feedback: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>('/feedback', { method: 'POST', body: payload }),
  feedbackReasons: () => request<{ code: string; label: string }[]>('/feedback/reasons', { auth: false }),

  // --- catalogue ---
  searchOpportunities: (params: Record<string, string>) =>
    request<{ items: Opportunity[]; total: number; distances_km: Record<string, number> }>(
      `/opportunities/search?${new URLSearchParams(params)}`,
    ),
  qualification: (code: string) => request<Record<string, any>>(`/qualifications/by-code/${code}`),

  // --- admin ---
  adminOpportunities: (params: Record<string, string> = {}) =>
    request<{ items: Opportunity[]; total: number }>(`/admin/opportunities?${new URLSearchParams(params)}`),
  createOpportunity: (payload: Record<string, unknown>) =>
    request<Opportunity>('/admin/opportunities', { method: 'POST', body: payload }),
  updateOpportunity: (id: string, payload: Record<string, unknown>) =>
    request<Opportunity>(`/admin/opportunities/${id}`, { method: 'PATCH', body: payload }),
  deleteOpportunity: (id: string) =>
    request<{ message: string }>(`/admin/opportunities/${id}`, { method: 'DELETE' }),
  verifyOpportunity: (id: string, payload: Record<string, unknown>) =>
    request<Opportunity>(`/admin/opportunities/${id}/verify`, { method: 'POST', body: payload }),
  importOpportunities: (file: File, dryRun: boolean) => {
    const form = new FormData()
    form.append('file', file)
    return request<Record<string, any>>(`/admin/opportunities/import?dry_run=${dryRun}`, {
      method: 'POST',
      formData: form,
    })
  },
  analytics: () => request<Analytics>('/admin/analytics'),
  audit: (params: Record<string, string> = {}) =>
    request<AuditEntry[]>(`/admin/audit?${new URLSearchParams(params)}`),
  adminBeneficiaries: () => request<Record<string, any>[]>('/admin/beneficiaries'),
  adminExtraction: (id: string) => request<Record<string, any>>(`/admin/beneficiaries/${id}/extraction`),
  adminRecommendations: (beneficiaryId: string) =>
    request<RecommendationRun>(`/recommendations/${beneficiaryId}`),
  overrideRecommendation: (id: string, payload: Record<string, unknown>) =>
    request<Record<string, any>>(`/admin/recommendations/${id}/override`, { method: 'POST', body: payload }),
  reindex: () => request<Record<string, any>>('/admin/knowledge/reindex', { method: 'POST' }),
}
