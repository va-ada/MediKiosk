/**
 * Types for every contract payload (CONTRACTS.md). Keep in sync with CONTRACTS.md — never invent fields.
 * JSON is snake_case; enum values are exactly as in §2.
 */

// ---------- §2 Enums ----------
export type Sex = 'M' | 'F' | 'O'
export type Language = 'hi' | 'en'
export type Role = 'doctor' | 'nurse' | 'desk' | 'admin'
export type Department = 'general' | 'ayurveda'
export type Informant = 'self' | 'proxy'
export type LegalBasis = 'consent' | 'medical_emergency'
export type SessionStatus =
  | 'identifying'
  | 'consented'
  | 'triaged'
  | 'history'
  | 'documents'
  | 'verifying'
  | 'submitted'
  | 'with_doctor'
  | 'closed'
export type Lane = 'emergency' | 'priority' | 'normal'
export type TokenStatus = 'waiting' | 'called' | 'in' | 'no_show' | 'absent' | 'done' | 'referred'
export type Outcome = 'out' | 'recheck' | 'refer' | 'followup'
export type AnswerSource = 'voice' | 'tap' | 'staff'
export type AnswerStatus = 'confident' | 'uncertain'
export type Section =
  | 'complaint'
  | 'hpi'
  | 'pmh'
  | 'drugs'
  | 'allergies'
  | 'family'
  | 'personal'
  | 'ros'
  | 'labs'
  | 'ayush'
export type Trust = 'patient_said' | 'from_report' | 'doctor_verified' | 'rejected'
export type SourceType = 'answer' | 'document' | 'doctor' | 'carried'
export type DocType = 'lab_report' | 'prescription' | 'discharge_summary' | 'unknown'
export type DocStatus = 'pending' | 'processed' | 'failed'
export type AlertLevel = 'urgent' | 'emergency'
export type AlertSource = 'button' | 'rule'
export type AlertStatus = 'open' | 'acknowledged' | 'confirmed' | 'downgraded'
export type ReasonCode =
  | 'chest_pain'
  | 'breathing'
  | 'bleeding'
  | 'unconscious'
  | 'seizure'
  | 'stroke_signs'
  | 'severe_pain'
  | 'pregnancy'
  | 'other'
export type ComplaintCode =
  | 'joint_pain'
  | 'fever'
  | 'cough'
  | 'stomach'
  | 'headache'
  | 'chest_pain'
  | 'breathing'
  | 'skin'
  | 'other'
export type ReadbackResponse = 'yes' | 'no' | 'not_sure'
export type OutboxStatus = 'pending' | 'sent' | 'skipped_no_consent' | 'failed'
export type DeviceMode = 'KIOSK' | 'HALL' | 'PATIENT_APP'
export type QuestionType = 'choice' | 'multi' | 'yesno' | 'number' | 'duration' | 'scale' | 'free'
export type SlotType =
  | 'string'
  | 'enum'
  | 'bool'
  | 'number'
  | 'duration_days'
  | 'scale_0_10'
  | 'list_enum'
  | 'list_string'

/** §2 section display order (doctor view). */
export const SECTION_ORDER: readonly Section[] = [
  'complaint',
  'hpi',
  'allergies',
  'drugs',
  'pmh',
  'labs',
  'family',
  'personal',
  'ros',
  'ayush',
]

export const COMPLAINT_CODES: readonly ComplaintCode[] = [
  'joint_pain',
  'fever',
  'cough',
  'stomach',
  'headache',
  'chest_pain',
  'breathing',
  'skin',
  'other',
]

/** Triage red-flag slots (§4.3 / §9.2), in the order they are asked. */
export type RedFlagSlot = 'chest_pain' | 'breathless' | 'stroke_signs' | 'heavy_bleeding' | 'fainted'
export type RedFlags = Record<RedFlagSlot, boolean>

// ---------- §1 errors ----------
export interface ApiErrorBody {
  error: { code: string; message: string }
}

// ---------- §4.1 staff ----------
export interface StaffPublic {
  id: string
  name: string
  role: Role
  department: Department | null
  room: string | null
}
export interface LoginRequest {
  staff_id: string
  pin: string
}
export interface LoginResponse {
  token: string
  staff: StaffPublic
}

// ---------- §3 records ----------
export interface Patient {
  id: string
  hospital_id: string
  name: string
  age: number
  sex: Sex
  language: Language
  abha_number: string | null
  created_at: string
}

export interface Session {
  id: string
  patient_id: string
  kiosk_id: string
  informant: Informant
  informant_relation: string | null
  status: SessionStatus
  legal_basis: LegalBasis
  complaint_code: ComplaintCode | null
  pathway: string | null
  department: Department | null
  created_at: string
  submitted_at: string | null
  opened_by_doctor_at: string | null
  closed_at: string | null
}

export interface Consent {
  id: string
  session_id: string
  capture: boolean
  scan: boolean
  share_hospital: boolean
  link_abha: boolean
  check_passed: boolean
  created_at: string
  revoked_at: string | null
}

/** [x, y, w, h] in image pixels. */
export type Bbox = [number, number, number, number]

export interface LabValue {
  test: string
  value: number | string | null
  unit: string | null
  ref_low: number | null
  ref_high: number | null
  flag: string | null
  date: string | null
}

export interface DrugValue {
  name: string | null
  name_as_written: string | null
  dose: string | null
  frequency: string | null
  duration: string | null
  matched: boolean
  found_in_documents: boolean
}

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }

export interface Fact {
  id: string
  session_id: string
  patient_id: string
  section: Section
  key: string
  value: JsonValue
  text_en: string
  patient_words: string | null
  trust: Trust
  source_type: SourceType
  source_id: string | null
  bbox: Bbox | null
  created_at: string
  verified_by: string | null
  verified_at: string | null
}

export interface Document {
  id: string
  session_id: string
  patient_id: string
  file_path?: string
  page_no: number
  doc_type: DocType
  doc_date: string | null
  ocr_json: JsonValue
  status: DocStatus
  pinned: boolean
  created_at: string
}

export interface Answer {
  id: string
  session_id: string
  question_id: string
  source: AnswerSource
  raw_text: string | null
  confidence: number | null
  slots: Record<string, JsonValue>
  status: AnswerStatus
  created_at: string
}

export interface Outbox {
  id: string
  kind: 'fhir_bundle'
  session_id: string
  patient_id: string
  /** Only with `?include_payload=true` (S16); the list omits it and sends `resource_count`. */
  payload?: JsonValue
  resource_count: number
  idempotency_key: string
  status: OutboxStatus
  attempts: number
  last_error: string | null
  next_attempt_at: string | null
  created_at: string
  sent_at: string | null
}

export interface AuditLog {
  id: number
  ts: string
  actor: string
  action: string
  entity: string
  entity_id: string
  details: JsonValue
  prev_hash: string
  hash: string
}

// ---------- §4.2 / §4.3 kiosk requests ----------
export interface RegisterRequest {
  name: string
  age: number
  sex: Sex
  language: Language
}
export interface AbhaVerifyRequest {
  abha_number: string
  otp: string
}
export interface SessionCreateRequest {
  patient_id: string
  informant: Informant
  informant_relation?: string
}
export interface ConsentRequest {
  capture: boolean
  scan: boolean
  share_hospital: boolean
  link_abha: boolean
  check_passed: boolean
}
export interface TriageRequest {
  complaint_code: ComplaintCode
  complaint_text?: string
  body_part?: string
  redflags: RedFlags
}
export interface TriageResponse {
  session: Session
  token: QueueItem | null
  alerts: Alert[]
}

// ---------- §11.2 QueueItem ----------
export type QueueFlag = 'red_flag' | 'aged' | 'recheck' | 'referred'
export interface QueuePatient {
  name: string
  age: number
  sex: Sex
  language: Language
}
export interface QueueItem {
  id: string
  display: string
  lane: Lane
  status: TokenStatus
  department: Department
  session_id: string
  patient: QueuePatient | null
  complaint: string | null
  arrival_seq: number
  created_at: string
  wait_min: number
  flags: QueueFlag[]
  called_count: number
  doctor_id: string | null
  doctor_name: string | null
  preferred_doctor_id: string | null
}
/** `token.called` event data (§5). */
export interface CalledQueueItem extends QueueItem {
  room: string | null
}

export interface NextRequest {
  department: Department
}
export interface OutcomeRequest {
  outcome: Outcome
  refer_department?: Department
  followup_date?: string
  results_tomorrow?: boolean
  admit?: boolean
  note?: string
}
export interface SignoutResponse {
  returned_tokens: number
}

// ---------- §11.3 Alert ----------
export interface Alert {
  id: string
  kiosk_id: string
  session_id: string | null
  level: AlertLevel
  reason_code: ReasonCode | null
  rule_id: string | null
  reason_text: string
  source: AlertSource
  status: AlertStatus
  escalated: boolean
  created_at: string
  acknowledged_by: string | null
  acknowledged_at?: string | null
  resolved_by: string | null
  resolved_at?: string | null
}
export interface EmergencyRequest {
  id: string
  kiosk_id: string
  reason_code: ReasonCode
  session_id?: string
}
export interface ResolveRequest {
  outcome: 'confirmed' | 'downgraded'
}

// ---------- §11.4 Question ----------
export type ChoiceValue = string | number | boolean
export interface Choice {
  value: ChoiceValue
  label?: string
  en: string
  hi: string
  icon?: string | null
}
export interface Question {
  id: string
  type: QuestionType
  section: Section
  text: string
  text_en: string
  audio: string
  choices: Choice[]
  slot: { name: string; type: SlotType }
  allow_voice: boolean
  progress: { answered: number; remaining_estimate: number }
}
export type NextQuestionResponse = { done: false; question: Question } | { done: true }
export interface AnswerRequest {
  question_id: string
  source: 'tap'
  value: JsonValue
}
export interface AnswerResponse {
  answer: Answer
  next: NextQuestionResponse
  alerts: Alert[]
}
export interface AudioAnswerResponse extends AnswerResponse {
  fallback_choices: Choice[]
}

// ---------- §4.5 read-back and submit ----------
export interface ReadbackItem {
  fact_id: string
  text: string
  text_en: string
}
export interface ReadbackResponseBody {
  items: ReadbackItem[]
}
export interface ReadbackRequest {
  fact_id: string
  response: ReadbackResponse
}
export interface SubmitResponse {
  session: Session
  summary_version: number
}

// ---------- §11.1 Summary ----------
export type FactFlag = 'unreadable' | 'patient_disputed' | 'patient_unsure' | 'carried'
export interface CriticalItem {
  fact_id: string
  text: string
  trust: Trust
}
export interface SummaryItem {
  fact_id: string
  text: string
  trust: Trust
  patient_words?: string | null
  flags: FactFlag[]
  found_in_documents?: boolean
  source?: { document_id: string; bbox: Bbox | null }
  /** Server extra (S12): Sanskrit/clinical term on AYUSH answer facts — doctor side only. */
  doctor_note?: string | null
}
/** Server extra (S12): `critical.red_flags` items come from alerts, not facts. */
export interface RedFlagItem {
  alert_id: string
  text: string
  level: AlertLevel
  status: AlertStatus
}
/** Server extra (S12): `new_since_opened` items. */
export interface NewSinceItem {
  fact_id: string
  section: Section
  text: string
}
export interface SummarySection {
  key: Section
  title: string
  opened: boolean
  approved: boolean
  narrative?: string | null
  /** Server extra (S12, hpi only): true when the narrative was written by the LLM — label it in the UI. */
  narrative_ai?: boolean
  items: SummaryItem[]
}
export interface SummaryDocument {
  id: string
  doc_type: DocType
  doc_date: string | null
  pinned: boolean
  image_url: string
  status: DocStatus
}
export interface Summary {
  session_id: string
  version: number
  generated_at: string
  patient: Omit<Patient, 'created_at'>
  informant: { type: Informant; relation: string | null }
  token: { display: string; department: Department }
  critical: {
    allergies: CriticalItem[]
    red_flags: RedFlagItem[]
    abnormal_labs: CriticalItem[]
  }
  sections: SummarySection[]
  documents: SummaryDocument[]
  new_since_opened: NewSinceItem[]
}

// ---------- §4.7 doctor review ----------
export interface OkResponse {
  ok: true
}
export interface VerifyFactRequest {
  action: 'approve' | 'edit' | 'reject'
  value?: JsonValue
  text_en?: string
}
/** Server extra (S14): each exam field accepts a plain string or `{value, note}`. */
export type AyushFinding = string | { value: string; note?: string }
export interface AyushExamRequest {
  nadi?: AyushFinding
  jihva?: AyushFinding
  pramana?: { height_cm: number; weight_kg: number }
  sara?: AyushFinding
  samhanana?: AyushFinding
  vikriti?: AyushFinding
  notes?: string
}
export interface TermCode {
  system: string
  code: string
  display: string
}
export interface DiagnosisRequest {
  codes: TermCode[]
  text?: string
}
export interface TerminologyResult extends TermCode {
  sample: boolean
}

// ---------- §11.5 DisplayState ----------
export interface NowServing {
  display: string
  doctor_name: string | null
  room: string | null
  called_at: string | null
}
export interface DisplayState {
  department: Department | null
  now_serving: NowServing[]
  next: string[]
}

// ---------- §4.9 admin ----------
export interface AdminHealth {
  db: boolean
  nlp: boolean
  relay: boolean
  his: boolean
  ollama: boolean
  island_mode: boolean
}
export interface IslandState {
  enabled: boolean
}
export interface AuditVerify {
  valid: boolean
  checked: number
  first_bad_id: number | null
}
export interface EraseRequest {
  approver_staff_id: string
  approver_pin: string
}

// ---------- §5 WebSocket ----------
export type WsChannel = 'queue' | 'alerts' | 'display' | 'admin'
type Ws<T extends string, D> = { type: T; data: D; ts: string }
export type WsMessage =
  | Ws<'token.created' | 'token.updated', QueueItem>
  | Ws<'token.called', CalledQueueItem>
  | Ws<'alert.created' | 'alert.updated', Alert>
  | Ws<'summary.ready', { session_id: string; version: number }>
  | Ws<'document.processed', Document>
  | Ws<'island.changed', IslandState>
export type WsEventType = WsMessage['type']

// ---------- §7 relay ----------
export interface RelayAlarm {
  id: string
  kiosk_id: string
  reason_code: ReasonCode
  created_at: string
}

/** Resume payload encoded in the token QR (§10.9). */
export interface ResumeQrPayload {
  session_id: string
  token_id: string
}
