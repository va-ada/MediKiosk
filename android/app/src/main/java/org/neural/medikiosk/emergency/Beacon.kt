package org.neural.medikiosk.emergency

import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.media.AudioManager
import android.media.ToneGenerator
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * The kiosk's own alarm (works with no network at all): a loud tone on the alarm stream and the torch blinking
 * at 1 Hz. The red/white screen flash is drawn by the emergency screen from [flashOn]-style ticks it owns.
 */
class Beacon(context: Context) {
    private val app = context.applicationContext
    private val audioManager = app.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private val cameraManager = app.getSystemService(Context.CAMERA_SERVICE) as CameraManager
    private var tone: ToneGenerator? = null
    private var job: Job? = null
    private var savedAlarmVolume: Int? = null
    private val torchId: String? = runCatching {
        cameraManager.cameraIdList.firstOrNull {
            cameraManager.getCameraCharacteristics(it).get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true
        }
    }.getOrNull()

    val running get() = job?.isActive == true

    fun start(scope: CoroutineScope, delayMs: Long = 0) {
        if (running) return
        job = scope.launch(Dispatchers.Default) {
            delay(delayMs)
            runCatching {
                savedAlarmVolume = audioManager.getStreamVolume(AudioManager.STREAM_ALARM)
                audioManager.setStreamVolume(AudioManager.STREAM_ALARM, audioManager.getStreamMaxVolume(AudioManager.STREAM_ALARM), 0)
                tone = ToneGenerator(AudioManager.STREAM_ALARM, ToneGenerator.MAX_VOLUME)
            }.onFailure { Log.w(TAG, "tone: ${it.message}") }
            Log.i(TAG, "beacon on (torch=${torchId ?: "none"})")
            var on = false
            while (isActive) {
                on = !on
                if (on) tone?.startTone(ToneGenerator.TONE_CDMA_HIGH_L, 450)
                torch(on)
                delay(500)
            }
        }
    }

    fun stop() {
        job?.cancel()
        job = null
        torch(false)
        tone?.release()
        tone = null
        savedAlarmVolume?.let { runCatching { audioManager.setStreamVolume(AudioManager.STREAM_ALARM, it, 0) } }
        savedAlarmVolume = null
        Log.i(TAG, "beacon off")
    }

    private fun torch(on: Boolean) {
        val id = torchId ?: return
        runCatching { cameraManager.setTorchMode(id, on) }
    }

    private companion object { const val TAG = "MediKioskBeacon" }
}
