package org.neural.medikiosk.data

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.neural.medikiosk.net.ApiClient
import org.neural.medikiosk.net.EmergencyRequest
import org.neural.medikiosk.net.RelayAlarm
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.concurrent.TimeUnit

/**
 * Emergency button network (§4.8 + §7): the alarm goes to the API server AND straight to the alarm relay,
 * in parallel, each capped at 3 s, failures ignored — the kiosk beacon never waits on either.
 */
class EmergencyRepository(private val settings: () -> DeviceSettings) {

    /** Returns (serverAccepted, relayAccepted). */
    suspend fun raise(id: String, reasonCode: String, sessionId: String?): Pair<Boolean, Boolean> = coroutineScope {
        val s = settings()
        val server = async(Dispatchers.IO) {
            withTimeoutOrNull(3000) {
                runCatching { ApiClient.api(s.serverUrl, s.deviceId, 3).emergency(EmergencyRequest(id, s.deviceId, reasonCode, sessionId)) }
                    .onFailure { Log.w(TAG, "server alarm failed: ${ApiClient.errorCode(it)}") }.isSuccess
            } ?: false
        }
        val relay = async(Dispatchers.IO) {
            withTimeoutOrNull(3000) {
                val now = Instant.now().truncatedTo(ChronoUnit.SECONDS).toString()
                runCatching { ApiClient.relay(s.relayUrl, s.deviceId).alarm(RelayAlarm(id, s.deviceId, reasonCode, now)) }
                    .onFailure { Log.w(TAG, "relay alarm failed: ${ApiClient.errorCode(it)}") }.isSuccess
            } ?: false
        }
        (server.await() to relay.await()).also { Log.i(TAG, "alarm $id server=${it.first} relay=${it.second}") }
    }

    /**
     * Listen on the server's `alerts` channel (§5) and call [onUpdated] when `alert.updated` arrives for [alertId]
     * (a nurse acknowledged / resolved it). Reconnects every 5 s while [isWanted] is true. Returns a closer.
     */
    fun watch(alertId: String, isWanted: () -> Boolean, onUpdated: (status: String) -> Unit): () -> Unit {
        val client = OkHttpClient.Builder().pingInterval(15, TimeUnit.SECONDS).build()
        var socket: WebSocket? = null
        var closed = false
        fun connect() {
            if (closed || !isWanted()) return
            val url = settings().serverUrl.trim().trimEnd('/').replaceFirst(Regex("^http"), "ws") + "/ws?channel=alerts"
            socket = client.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
                override fun onMessage(webSocket: WebSocket, text: String) {
                    runCatching {
                        val msg = ApiClient.json.parseToJsonElement(text).jsonObject
                        val data = msg["data"]?.jsonObject ?: return
                        if (msg["type"]?.jsonPrimitive?.content == "alert.updated" && data["id"]?.jsonPrimitive?.content == alertId) {
                            onUpdated(data["status"]?.jsonPrimitive?.content ?: "")
                        }
                    }
                }
                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    Log.w(TAG, "alerts ws: ${t.message}")
                    Thread { Thread.sleep(5000); connect() }.start()
                }
            })
        }
        connect()
        return { closed = true; socket?.close(1000, null); client.dispatcher.executorService.shutdown() }
    }

    private companion object { const val TAG = "MediKioskEmergency" }
}
