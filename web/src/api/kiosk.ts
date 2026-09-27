/**
 * Kiosk endpoints called from the assisted desk page. They use `X-Kiosk-Id: DESK-01` and no Bearer token (§1).
 */
import { api, type ApiOptions } from './client'
import type {
  Consent,
  ConsentRequest,
  Patient,
  RegisterRequest,
  Session,
  SessionCreateRequest,
  TriageRequest,
  TriageResponse,
} from './types'

export const DESK_KIOSK_ID = 'DESK-01'
const DESK: ApiOptions = { auth: false, headers: { 'X-Kiosk-Id': DESK_KIOSK_ID } }

export const registerPatient = (body: RegisterRequest): Promise<Patient> =>
  api<Patient>('POST', '/api/patients/register', body, DESK)

export const createSession = (body: SessionCreateRequest): Promise<Session> =>
  api<Session>('POST', '/api/sessions', body, DESK)

export const giveConsent = (sessionId: string, body: ConsentRequest): Promise<Consent> =>
  api<Consent>('POST', `/api/sessions/${sessionId}/consent`, body, DESK)

export const triage = (sessionId: string, body: TriageRequest): Promise<TriageResponse> =>
  api<TriageResponse>('POST', `/api/sessions/${sessionId}/triage`, body, DESK)

/** Staff explain consent verbally at the desk, so every toggle is recorded as agreed. */
export const DESK_CONSENT: ConsentRequest = {
  capture: true,
  scan: true,
  share_hospital: true,
  link_abha: true,
  check_passed: true,
}

export interface WalkIn {
  patient: RegisterRequest
  session: Omit<SessionCreateRequest, 'patient_id'>
  triage: TriageRequest
}

/** How far a walk-in registration got — pass it back in to resume after a failure without duplicating records. */
export interface WalkInProgress {
  patient?: Patient
  session?: Session
  consented?: boolean
  result?: TriageResponse
}

/**
 * register → session → consent → triage. `progress` is updated in place after each step, so a retry with the
 * same object continues where it stopped (triage itself is idempotent on the server).
 */
export async function registerWalkIn(input: WalkIn, progress: WalkInProgress): Promise<TriageResponse> {
  progress.patient ??= await registerPatient(input.patient)
  progress.session ??= await createSession({ ...input.session, patient_id: progress.patient.id })
  if (!progress.consented) {
    await giveConsent(progress.session.id, DESK_CONSENT)
    progress.consented = true
  }
  progress.result ??= await triage(progress.session.id, input.triage)
  return progress.result
}
