package org.neural.medikiosk.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
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

/** The §1 error code of a failed [Result]. */
fun Result<*>.errorCode(): String? = exceptionOrNull()?.let { (it as? ApiFailure)?.code ?: "unknown_error" }
