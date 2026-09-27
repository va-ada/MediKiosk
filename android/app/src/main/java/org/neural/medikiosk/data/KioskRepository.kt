package org.neural.medikiosk.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import org.neural.medikiosk.net.Api
import org.neural.medikiosk.net.ApiClient
import kotlin.coroutines.cancellation.CancellationException

/** A failed server call, carrying the §1 error code (`network_error` when unreachable). */
class ApiFailure(val code: String, cause: Throwable? = null) : Exception(code, cause)

/**
 * The kiosk's only way to the server (CLAUDE.md §8: network in repositories). Wraps [Api] built from the
 * current device settings and turns every failure into an [ApiFailure] with the contract's error code.
 */
class KioskRepository(private val settings: () -> DeviceSettings) {
    private var cache: Triple<String, String, Api>? = null

    fun api(): Api {
        val s = settings()
        cache?.let { (url, id, api) -> if (url == s.serverUrl && id == s.deviceId) return api }
        return ApiClient.api(s.serverUrl, s.deviceId).also { cache = Triple(s.serverUrl, s.deviceId, it) }
    }

    suspend fun <T> call(block: suspend Api.() -> T): Result<T> = withContext(Dispatchers.IO) {
        try {
            Result.success(api().block())
        } catch (c: CancellationException) {
            throw c
        } catch (t: Throwable) {
            Result.failure(ApiFailure(ApiClient.errorCode(t), t))
        }
    }
}

/** Voice answer upload (multipart `question_id`, `language`, `audio`, §4.3). The caller deletes [clip] afterwards. */
suspend fun KioskRepository.answerAudio(sessionId: String, questionId: String, language: String, clip: File) = call {
    val text = "text/plain".toMediaType()
    answerAudio(
        sessionId,
        questionId.toRequestBody(text),
        language.toRequestBody(text),
        MultipartBody.Part.createFormData("audio", clip.name, clip.asRequestBody("audio/mp4".toMediaType())),
    )
}

/** Document page upload (multipart `image` jpeg/png, `page_no`, §4.4). */
suspend fun KioskRepository.uploadDocument(sessionId: String, pageNo: Int, image: File) = call {
    val type = if (image.extension.lowercase() == "png") "image/png" else "image/jpeg"
    uploadDocument(
        sessionId,
        MultipartBody.Part.createFormData("image", image.name, image.asRequestBody(type.toMediaType())),
        pageNo.toString().toRequestBody("text/plain".toMediaType()),
    )
}

/** The §1 error code of a failed [Result]. */
fun Result<*>.errorCode(): String? = exceptionOrNull()?.let { (it as? ApiFailure)?.code ?: "unknown_error" }
