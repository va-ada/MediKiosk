package org.neural.medikiosk.net

import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.RequestBody
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Kiosk endpoints (CONTRACTS.md §4.2–4.5, §4.8, health). Every call carries `X-Kiosk-Id` (see [ApiClient]). */
interface Api {
    @GET("api/health") suspend fun health(): Health

    @POST("api/patients/register") suspend fun register(@Body body: RegisterRequest): Patient
    @POST("api/patients/abha/verify") suspend fun abhaVerify(@Body body: AbhaVerifyRequest): Patient
    @GET("api/patients/{id}") suspend fun patient(@Path("id") id: String): Patient

    @POST("api/sessions") suspend fun createSession(@Body body: SessionCreateRequest): Session
    @GET("api/sessions/{id}") suspend fun session(@Path("id") id: String): Session
    @POST("api/sessions/{id}/consent") suspend fun consent(@Path("id") id: String, @Body body: ConsentRequest): Consent
    @POST("api/sessions/{id}/triage") suspend fun triage(@Path("id") id: String, @Body body: TriageRequest): TriageResponse

    @GET("api/sessions/{id}/next-question")
    suspend fun nextQuestion(@Path("id") id: String, @Query("language") language: String): NextQuestion

    @POST("api/sessions/{id}/answers")
    suspend fun answer(@Path("id") id: String, @Body body: AnswerRequest, @Query("language") language: String): AnswerResponse

    @Multipart
    @POST("api/sessions/{id}/answers/audio")
    suspend fun answerAudio(
        @Path("id") id: String,
        @Part("question_id") questionId: RequestBody,
        @Part("language") language: RequestBody,
        @Part audio: MultipartBody.Part,
    ): AnswerResponse

    @Multipart
    @POST("api/sessions/{id}/documents")
    suspend fun uploadDocument(@Path("id") id: String, @Part image: MultipartBody.Part, @Part("page_no") pageNo: RequestBody): Document
    @GET("api/documents/{id}") suspend fun document(@Path("id") id: String): Document

    @GET("api/sessions/{id}/readback") suspend fun readback(@Path("id") id: String, @Query("language") language: String): ReadbackList
    @POST("api/sessions/{id}/readback") suspend fun readbackAnswer(@Path("id") id: String, @Body body: ReadbackRequest): Ok
    @POST("api/sessions/{id}/submit") suspend fun submit(@Path("id") id: String): SubmitResponse

    @POST("api/alerts/emergency") suspend fun emergency(@Body body: EmergencyRequest): Alert
    @POST("api/tokens/{id}/reactivate") suspend fun reactivate(@Path("id") id: String): QueueItem
    @GET("api/display/state") suspend fun displayState(@Query("department") department: String?): DisplayState
}

/** Alarm relay (§7) — a separate service so the emergency path works even when the API server is down. */
interface RelayApi {
    @POST("alarm") suspend fun alarm(@Body body: RelayAlarm): kotlinx.serialization.json.JsonObject
    @GET("health") suspend fun health(): kotlinx.serialization.json.JsonObject
}

object ApiClient {
    val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

    private fun http(deviceId: String, timeoutSec: Long): OkHttpClient {
        val kioskHeader = Interceptor { chain -> chain.proceed(chain.request().newBuilder().header("X-Kiosk-Id", deviceId).build()) }
        return OkHttpClient.Builder()
            .addInterceptor(kioskHeader)
            .addInterceptor(HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC })
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(timeoutSec, TimeUnit.SECONDS)
            .writeTimeout(timeoutSec, TimeUnit.SECONDS)
            .build()
    }

    private fun base(url: String) = url.trim().trimEnd('/') + "/"

    /** Voice and document uploads wait on ASR/LLM/OCR, so reads get a generous timeout. */
    fun api(serverUrl: String, deviceId: String, timeoutSec: Long = 90): Api = Retrofit.Builder()
        .baseUrl(base(serverUrl))
        .client(http(deviceId, timeoutSec))
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()
        .create(Api::class.java)

    /** Emergency calls use short timeouts (3 s): the beacon must never wait on the network. */
    fun relay(relayUrl: String, deviceId: String): RelayApi = Retrofit.Builder()
        .baseUrl(base(relayUrl))
        .client(http(deviceId, 3))
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()
        .create(RelayApi::class.java)

    /** The §1 error code of a failed call (`network_error` when the server couldn't be reached). */
    fun errorCode(t: Throwable): String = when (t) {
        is HttpException -> runCatching {
            json.decodeFromString(ErrorBody.serializer(), t.response()?.errorBody()?.string().orEmpty()).error.code
        }.getOrDefault("http_${t.code()}")
        is IOException -> "network_error"
        else -> "unknown_error"
    }
}
