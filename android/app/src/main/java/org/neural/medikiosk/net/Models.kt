package org.neural.medikiosk.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/* Data classes mirroring CONTRACTS.md (§2 enums as the exact wire strings, §4 requests, §11 payloads).
 * JSON is snake_case on the wire; @SerialName keeps Kotlin names idiomatic. Unknown fields are ignored. */

object Sex { const val M = "M"; const val F = "F"; const val O = "O" }
object Lang { const val HI = "hi"; const val EN = "en" }
object InformantType { const val SELF = "self"; const val PROXY = "proxy" }
object DeviceMode { const val KIOSK = "KIOSK"; const val HALL = "HALL"; const val PATIENT_APP = "PATIENT_APP" }
object QuestionType {
    const val CHOICE = "choice"; const val MULTI = "multi"; const val YESNO = "yesno"; const val NUMBER = "number"
    const val DURATION = "duration"; const val SCALE = "scale"; const val FREE = "free"
}
object ReadbackResponse { const val YES = "yes"; const val NO = "no"; const val NOT_SURE = "not_sure" }
val COMPLAINT_CODES = listOf("joint_pain", "fever", "cough", "stomach", "headache", "chest_pain", "breathing", "skin", "other")
val REASON_CODES = listOf("chest_pain", "breathing", "bleeding", "unconscious", "seizure", "stroke_signs", "severe_pain", "pregnancy", "other")

@Serializable data class Health(val status: String, val version: String)

@Serializable
data class Patient(
    val id: String,
    @SerialName("hospital_id") val hospitalId: String,
    val name: String,
    val age: Int,
    val sex: String,
    val language: String,
    @SerialName("abha_number") val abhaNumber: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
)

@Serializable data class RegisterRequest(val name: String, val age: Int, val sex: String, val language: String)
@Serializable data class AbhaVerifyRequest(@SerialName("abha_number") val abhaNumber: String, val otp: String)

@Serializable
data class Session(
    val id: String,
    @SerialName("patient_id") val patientId: String,
    @SerialName("kiosk_id") val kioskId: String,
    val informant: String,
    @SerialName("informant_relation") val informantRelation: String? = null,
    val status: String,
    @SerialName("legal_basis") val legalBasis: String,
    @SerialName("complaint_code") val complaintCode: String? = null,
    val pathway: String? = null,
    val department: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("submitted_at") val submittedAt: String? = null,
)

@Serializable
data class SessionCreateRequest(
    @SerialName("patient_id") val patientId: String,
    val informant: String,
    @SerialName("informant_relation") val informantRelation: String? = null,
)

@Serializable
data class ConsentRequest(
    val capture: Boolean,
    val scan: Boolean,
    @SerialName("share_hospital") val shareHospital: Boolean,
    @SerialName("link_abha") val linkAbha: Boolean,
    @SerialName("check_passed") val checkPassed: Boolean,
)

@Serializable data class Consent(val id: String, @SerialName("session_id") val sessionId: String)

@Serializable
data class RedFlags(
    @SerialName("chest_pain") val chestPain: Boolean,
    val breathless: Boolean,
    @SerialName("stroke_signs") val strokeSigns: Boolean,
    @SerialName("heavy_bleeding") val heavyBleeding: Boolean,
    val fainted: Boolean,
)

@Serializable
data class TriageRequest(
    @SerialName("complaint_code") val complaintCode: String,
    @SerialName("complaint_text") val complaintText: String? = null,
    @SerialName("body_part") val bodyPart: String? = null,
    val redflags: RedFlags,
)

@Serializable data class QueuePatient(val name: String, val age: Int, val sex: String, val language: String)

/** §11.2 */
@Serializable
data class QueueItem(
    val id: String,
    val display: String,
    val lane: String,
    val status: String,
    val department: String,
    @SerialName("session_id") val sessionId: String,
    val patient: QueuePatient? = null,
    val complaint: String? = null,
    @SerialName("arrival_seq") val arrivalSeq: Int,
    @SerialName("wait_min") val waitMin: Int = 0,
    val flags: List<String> = emptyList(),
)

/** §11.3 */
@Serializable
data class Alert(
    val id: String,
    @SerialName("kiosk_id") val kioskId: String,
    @SerialName("session_id") val sessionId: String? = null,
    val level: String,
    @SerialName("reason_code") val reasonCode: String? = null,
    @SerialName("reason_text") val reasonText: String,
    val status: String,
    val escalated: Boolean = false,
)

@Serializable data class TriageResponse(val session: Session, val token: QueueItem, val alerts: List<Alert> = emptyList())

@Serializable
data class Choice(
    val value: JsonElement,
    val label: String,
    val en: String? = null,
    val hi: String? = null,
    val icon: String? = null,
)

@Serializable data class SlotSpec(val name: String, val type: String)
@Serializable data class Progress(val answered: Int, @SerialName("remaining_estimate") val remainingEstimate: Int)

/** §11.4 — `text` is in the requested language; `allow_voice` is false where ASR can't help (English). */
@Serializable
data class Question(
    val id: String,
    val type: String,
    val section: String,
    val text: String,
    @SerialName("text_en") val textEn: String,
    val audio: String,
    val choices: List<Choice> = emptyList(),
    val slot: SlotSpec,
    @SerialName("allow_voice") val allowVoice: Boolean = true,
    val progress: Progress? = null,
)

@Serializable data class NextQuestion(val done: Boolean, val question: Question? = null)

@Serializable
data class AnswerRequest(
    @SerialName("question_id") val questionId: String,
    val source: String = "tap",
    val value: JsonElement,
)

@Serializable
data class Answer(
    val id: String,
    @SerialName("question_id") val questionId: String,
    val source: String,
    @SerialName("raw_text") val rawText: String? = null,
    val status: String,
)

@Serializable
data class AnswerResponse(
    val answer: Answer,
    val next: NextQuestion,
    val alerts: List<Alert> = emptyList(),
    @SerialName("fallback_choices") val fallbackChoices: List<Choice> = emptyList(),
)

@Serializable
data class Document(
    val id: String,
    @SerialName("session_id") val sessionId: String,
    @SerialName("page_no") val pageNo: Int,
    @SerialName("doc_type") val docType: String,
    @SerialName("doc_date") val docDate: String? = null,
    val status: String,
    val pinned: Boolean = false,
)

@Serializable data class ReadbackItem(@SerialName("fact_id") val factId: String, val text: String, @SerialName("text_en") val textEn: String)
@Serializable data class ReadbackList(val items: List<ReadbackItem>)
@Serializable data class ReadbackRequest(@SerialName("fact_id") val factId: String, val response: String)
@Serializable data class Ok(val ok: Boolean)
@Serializable data class SubmitResponse(val session: Session, @SerialName("summary_version") val summaryVersion: Int)

@Serializable
data class EmergencyRequest(
    val id: String,
    @SerialName("kiosk_id") val kioskId: String,
    @SerialName("reason_code") val reasonCode: String,
    @SerialName("session_id") val sessionId: String? = null,
)

/** §7 relay alarm */
@Serializable
data class RelayAlarm(
    val id: String,
    @SerialName("kiosk_id") val kioskId: String,
    @SerialName("reason_code") val reasonCode: String,
    @SerialName("created_at") val createdAt: String,
)

@Serializable data class NowServing(val display: String, @SerialName("doctor_name") val doctorName: String? = null, val room: String? = null)

/** §11.5 */
@Serializable
data class DisplayState(val department: String? = null, @SerialName("now_serving") val nowServing: List<NowServing> = emptyList(), val next: List<String> = emptyList())

/** §1 error body */
@Serializable data class ErrorBody(val error: ErrorDetail)
@Serializable data class ErrorDetail(val code: String, val message: String)

/** Token QR payload (§10.9) */
@Serializable data class TokenQr(@SerialName("session_id") val sessionId: String, @SerialName("token_id") val tokenId: String)
