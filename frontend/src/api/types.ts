/** Response shapes mirroring the FastAPI schemas. */

export type Role = 'beneficiary' | 'admin' | 'provider' | 'counsellor'

export interface User {
  id: string
  email: string
  full_name: string
  role: Role
  preferred_language: string
  is_active: boolean
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in_minutes: number
}

export interface AuthResponse {
  user: User
  tokens: TokenPair
}

export interface SlotOption {
  value: string
  label: string
  icon: string | null
}

export interface Slot {
  name: string
  priority: number
  required: boolean
  input_type: 'free_text' | 'choice' | 'location'
  question: string
  help: string | null
  depends_on: string | null
  options: SlotOption[]
}

export interface ConversationMessage {
  id: string
  sequence: number
  role: 'beneficiary' | 'assistant' | 'system'
  raw_text: string
  detected_language: string | null
  asr_confidence: number | null
  is_code_switched: boolean
  needs_confirmation: boolean
  created_at: string | null
}

export interface Progress {
  filled: string[]
  required: string[]
  required_filled: string[]
  percent: number
}

export interface Conversation {
  id: string
  beneficiary_id: string
  state: string
  language: string
  channel: string
  pending_slot: Slot | null
  draft_profile: DraftProfile
  progress: Progress
  messages: ConversationMessage[]
}

export interface ConversationStart {
  conversation: Conversation
  assistant_message: string
  slots: Slot[]
  speech_language_tag: string
  speech_provider: string
}

export interface ExtractedFact {
  value: string | number | null
  confidence: number
  evidence: string
  extractor?: string
  label?: string
}

export interface DraftSkill {
  code: string
  name: string
  raw_label: string
  proficiency: string
  confidence: string
  source: string
  verification_status: string
  years_experience: number | null
  evidence: string
  is_category: boolean
}

export interface DraftProfile {
  education?: ExtractedFact | null
  occupations?: ExtractedFact[]
  /** Work the person said they stopped doing. */
  previous_occupations?: ExtractedFact[]
  skills?: DraftSkill[]
  interests?: ExtractedFact[]
  goals?: ExtractedFact[]
  constraints?: (ExtractedFact & { kind: string })[]
  mobility?: ExtractedFact | null
  max_travel_km?: ExtractedFact | null
  experience_years?: ExtractedFact | null
  age?: ExtractedFact | null
  target_income?: ExtractedFact | null
  location?: Record<string, unknown> | null
}

/** One fact a turn added, already worded by the server ("Pump repair"). */
export interface UnderstoodFact {
  slot: string
  label: string
}

export interface MessageResponse {
  conversation_id: string
  /** Server id of the stored beneficiary message. */
  message_id: string | null
  client_message_id: string | null
  /** Language the assistant answered in. */
  language: string
  transcript: string
  transcript_confidence: number | null
  assistant_message: string
  next_question: string
  next_slot: string | null
  current_state: 'active' | 'awaiting_confirmation'
  pending_slot: Slot | null
  draft_profile: DraftProfile
  profile_update: UnderstoodFact[]
  extraction: Record<string, unknown> | null
  newly_filled: string[]
  needs_confirmation: boolean
  ready_to_confirm: boolean
  transcript_for_correction: string | null
  /** The answer was not understood and the question was asked differently. */
  clarification: boolean
  /** The stored result of an already-processed message id. */
  replayed: boolean
  progress: Progress
}

export interface ProfileSkill {
  id: string
  skill_id: string | null
  code: string | null
  name: string
  raw_label: string
  proficiency: string
  source: string
  confidence: string
  verification_status: string
  years_experience: number | null
  evidence: { type: string; description: string }[]
}

export interface BeneficiaryProfile {
  id: string
  user_id: string
  display_name: string
  preferred_language: string
  age: number | null
  gender: string | null
  mobility: 'low' | 'medium' | 'high'
  max_travel_km: number | null
  is_confirmed: boolean
  confirmed_at: string | null
  education: { level: string; label: string; source: string; confidence: string; verification_status: string } | null
  occupations: { id: string; title: string; sector: string | null; is_current: boolean; source: string; confidence: string }[]
  experiences: { id: string; title: string; years: number | null; nature: string; verification_status: string }[]
  skills: ProfileSkill[]
  interests: { id: string; label: string; tag: string | null; strength: number }[]
  goals: { id: string; goal_type: string; description: string | null; target_monthly_income_inr: number | null; priority: number }[]
  constraints: { id: string; kind: string; label: string; severity: string }[]
  location: LocationOut | null
}

export interface LocationOut {
  id?: string | null
  label?: string | null
  village?: string | null
  block?: string | null
  district?: string | null
  state?: string | null
  pincode?: string | null
  latitude?: number | null
  longitude?: number | null
  source?: string | null
  accuracy_m?: number | null
  captured_at?: string | null
}

export interface SkillGraphNode {
  code: string
  name: string
  score: number
  is_direct: boolean
  is_category: boolean
  proficiency: string | null
  source: string | null
  confidence: string | null
  verification_status: string | null
  evidence_strength: number
  years_experience: number | null
  derived_from: string | null
  derivation: string | null
}

export interface SkillGraph {
  nodes: SkillGraphNode[]
  edges: { source: string; target: string; relation: string; weight: number }[]
}

export interface CompetencyCoverage {
  code: string
  name: string
  nos_code: string | null
  is_core: boolean
  weight: number
  coverage: number
  band: 'covered' | 'partial' | 'missing'
  contributing_skills: {
    skill_code: string
    skill_name: string
    your_level: number
    counts_towards: number
    contribution: number
    is_direct: boolean
    derivation: string | null
    verification_status: string | null
  }[]
  explanation: string
}

export interface SkillGapReport {
  qualification_id: string
  qualification_code: string | null
  qualification_title: string
  nsqf_level: number | null
  coverage_ratio: number
  gap_ratio: number
  gap_band: 'small' | 'moderate' | 'large'
  covered: CompetencyCoverage[]
  partial: CompetencyCoverage[]
  missing: CompetencyCoverage[]
  priority_order: string[]
  target_graph?: { nodes: Record<string, unknown>[]; edges: Record<string, unknown>[] }
  minimum_education?: string | null
  source?: string
}

export interface QualificationSummary {
  id: string
  code: string | null
  title: string
  occupation_role: string
  sector: string
  nsqf_level: number | null
  status: string
  minimum_education: string | null
  source: string
  last_verified_at: string | null
  superseded_by_code: string | null
}

export interface Recommendation {
  id: string
  pathway_id: string
  rank: number
  title: string
  provider: string
  opportunity_type: string
  match_score: number
  skill_fit: string
  eligibility: string
  distance_km: number | null
  mobility_fit: string
  availability: string
  skill_gap: string
  skill_gaps: string[]
  missing_competencies: { code: string; name: string; nos_code: string | null }[]
  skills_you_have: { code: string; name: string }[]
  why_it_fits: string[]
  cautions: string[]
  next_step: string
  source: string
  source_url: string | null
  verification_status: string
  last_verified_at: string | null
  valid_until: string | null
  seats_available: number | null
  stipend_or_income_inr: number | null
  location_label: string | null
  district: string | null
  qualification: QualificationSummary | null
  is_selected: boolean
  is_overridden: boolean
  override_action: string | null
}

export interface NoMatch {
  message: string
  closest_pathway: Record<string, any> | null
  missing_competencies: { code: string; name: string; nos_code: string | null; explanation: string }[]
  prerequisite_suggestions: { competency_code: string; competency_name: string; suggestion: string }[]
  what_to_verify: string[]
  retry_options: { action: string; label: string; detail: string }[]
}

export interface RankingWeight {
  code: string
  label: string
  weight: number
  share: number
}

export interface RecommendationRun {
  beneficiary_id: string
  run_id: string
  generated_at: string
  mobility_used: string
  radius_km_used: number | null
  candidates_considered: number
  candidates_after_filters: number
  is_no_match: boolean
  no_match: NoMatch | null
  recommendations: Recommendation[]
  exclusions: { opportunity_id: string; title: string; reason_code: string; reason: string; detail: string | null }[]
  ranking_weights: RankingWeight[]
  duration_ms: number | null
}

export interface Factor {
  code: string
  label: string
  score: number
  weight: number
  contribution: number
  detail: string | null
}

export interface Reason {
  category: string
  code: string
  label: string
  detail: string | null
  contribution: number | null
}

export interface Explanation {
  recommendation_id: string
  pathway_id: string
  title: string
  match_score: number
  factors: Factor[]
  why_it_fits: Reason[]
  what_is_missing: Reason[]
  cautions: Reason[]
  next_step: Reason | null
  skill_gap_detail: SkillGapReport | null
  evidence: Record<string, any>
  method_note: string
}

export interface Outcome {
  id: string
  beneficiary_id: string
  opportunity_id: string
  recommendation_id: string | null
  qualification_id: string | null
  status: string
  status_history: { from: string | null; to: string; at: string; actor: string; note: string | null }[]
  outcome_type: string | null
  monthly_income_inr: number | null
  exit_reason: string | null
  notes: string | null
  is_active: boolean
  selected_at: string | null
  enrolled_at: string | null
  started_at: string | null
  completed_at: string | null
  employment_at: string | null
  allowed_next: string[]
  opportunity: { id: string; title: string; provider: string; type: string } | null
}

export interface Opportunity {
  id: string
  title: string
  provider: string
  opportunity_type: string
  description: string
  sector: string | null
  qualification_id: string | null
  qualification: QualificationSummary | null
  skills_required: string[]
  skill_codes: string[]
  competencies_required: string[]
  education_required: string | null
  min_age: number | null
  max_age: number | null
  eligibility_notes: string | null
  location_label: string | null
  village: string | null
  block: string | null
  district: string | null
  state: string | null
  pincode: string | null
  latitude: number | null
  longitude: number | null
  mobility_required: string
  stipend_or_income_inr: number | null
  seats_total: number | null
  seats_available: number | null
  source: string
  source_url: string | null
  ingestion_channel: string
  source_trust: number
  verification_status: string
  status: string
  last_verified_at: string | null
  valid_from: string | null
  valid_until: string | null
  external_id: string | null
  training_program: Record<string, any> | null
  created_at: string
  updated_at: string
}

export interface ProviderStatus {
  name: string
  kind: string
  configured: boolean
  detail: string
  is_offline_default: boolean
}

export interface SystemStatus {
  app_name: string
  version: string
  environment: string
  demo_mode: boolean
  database: string
  providers: Record<string, ProviderStatus[]>
  capabilities: Record<string, boolean>
}

export interface Analytics {
  is_demo_data: boolean
  disclaimer?: string
  generated_at: string
  beneficiaries: { total: number; profile_confirmed: number; profile_unconfirmed: number }
  opportunities: {
    total: number
    active: number
    inactive: number
    expired: number
    stale_needs_reverification: number
    excluded_as_hard_stale: number
    verified: number
    by_type: Record<string, number>
    by_sector: Record<string, number>
  }
  recommendations: {
    runs: number
    no_match_runs: number
    generated: number
    selected: number
    overridden: number
    acceptance_rate: number | null
    average_distance_km: number | null
  }
  outcomes: Record<string, any>
  feedback: {
    total: number
    found_useful: number
    average_rating: number | null
    rejection_reasons: { code: string; label: string; count: number }[]
  }
  users: { total: number; by_role: Record<string, number> }
  top_skill_gaps: { code: string; name: string; count: number }[]
  opportunity_freshness: {
    id: string
    title: string
    provider: string
    status: string
    verification_status: string
    last_verified_at: string | null
    days_since_verified: number | null
    valid_until: string | null
  }[]
}

export interface AuditEntry {
  id: string
  created_at: string
  action: string
  actor_email: string | null
  actor_role: string | null
  entity_type: string | null
  entity_id: string | null
  old_value: Record<string, any> | null
  new_value: Record<string, any> | null
  summary: string | null
  ip_address: string | null
}

export interface LanguageOption {
  code: string
  label: string
  speech_tag: string
}

export interface DemoSession {
  user: User
  beneficiary_id: string
  conversation_id: string
  assistant_message: string
  tokens: TokenPair
  location: Record<string, unknown>
  script: { step: number; language: string; text: string; note: string }[]
  note: string
}
