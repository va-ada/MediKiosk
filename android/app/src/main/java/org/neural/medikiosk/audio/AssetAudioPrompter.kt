package org.neural.medikiosk.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.media.MediaPlayer
import android.os.Build
import android.speech.tts.TextToSpeech
import android.util.Log
import java.util.Locale

/**
 * Plays `assets/audio/<lang>/<key>.wav` (copied from content/audio by the `copyAudio` Gradle task).
 * Screens without a recorded prompt are spoken with Android TextToSpeech (hi-IN / en-IN; silent if unavailable).
 *
 * [handset]: route prompts to the earpiece (MODE_IN_COMMUNICATION, speakerphone off) so the patient holds the
 * phone to the ear; otherwise the loudspeaker. [slow]: playback speed 0.85.
 */
class AssetAudioPrompter(context: Context) : AudioPrompter {
    private val app = context.applicationContext
    private val audioManager = app.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private var player: MediaPlayer? = null
    private var playingKey: String? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false

    var handset: Boolean = false
        set(value) { field = value; applyRoute() }
    var slow: Boolean = false

    init {
        tts = TextToSpeech(app) { status -> ttsReady = status == TextToSpeech.SUCCESS }
    }

    private val speed get() = if (slow) 0.85f else 1f

    private fun attributes(): AudioAttributes = AudioAttributes.Builder()
        .setUsage(if (handset) AudioAttributes.USAGE_VOICE_COMMUNICATION else AudioAttributes.USAGE_MEDIA)
        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
        .build()

    /** Earpiece in handset mode, loudspeaker otherwise. */
    @Suppress("DEPRECATION")
    private fun applyRoute() {
        runCatching {
            if (handset) {
                audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
                if (Build.VERSION.SDK_INT >= 31) {
                    audioManager.availableCommunicationDevices.firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_EARPIECE }
                        ?.let { audioManager.setCommunicationDevice(it) }
                } else {
                    audioManager.isSpeakerphoneOn = false
                }
            } else {
                if (Build.VERSION.SDK_INT >= 31) audioManager.clearCommunicationDevice()
                audioManager.mode = AudioManager.MODE_NORMAL
            }
            Log.i(TAG, "audio route: ${if (handset) "earpiece (MODE_IN_COMMUNICATION)" else "speaker (MODE_NORMAL)"}")
        }.onFailure { Log.w(TAG, "audio route: ${it.message}") }
    }

    override fun play(key: String, lang: String) {
        stop()
        val path = "audio/$lang/$key.wav"
        runCatching {
            val afd = app.assets.openFd(path)
            val mp = MediaPlayer()
            mp.setAudioAttributes(attributes())
            mp.setDataSource(afd.fileDescriptor, afd.startOffset, afd.length)
            afd.close()
            mp.prepare()
            if (speed != 1f) mp.playbackParams = mp.playbackParams.setSpeed(speed)
            mp.setOnCompletionListener { if (player === it) stop() }
            mp.start()
            player = mp
            playingKey = key
            Log.i(TAG, "play $path speed=$speed handset=$handset")
        }.onFailure { Log.w(TAG, "play $path failed: ${it.message}") }
    }

    override fun speak(text: String, lang: String) {
        stop()
        val engine = tts ?: return
        if (!ttsReady) { Log.i(TAG, "speak skipped (TTS not ready): $text"); return }
        val locale = Locale.forLanguageTag(if (lang == "hi") "hi-IN" else "en-IN")
        if (engine.isLanguageAvailable(locale) < TextToSpeech.LANG_AVAILABLE) {
            Log.i(TAG, "speak skipped (no $locale voice)"); return
        }
        engine.language = locale
        engine.setSpeechRate(speed)
        engine.setAudioAttributes(attributes())
        engine.speak(text, TextToSpeech.QUEUE_FLUSH, null, "mk")
        playingKey = "tts:$text"
        Log.i(TAG, "speak [$lang] $text")
    }

    override fun stop() {
        player?.let { runCatching { it.stop() }; it.release() }
        player = null
        tts?.stop()
        playingKey = null
    }

    override fun stopIfPlaying(key: String) {
        if (playingKey == key) stop()
    }

    fun release() {
        stop()
        tts?.shutdown()
        tts = null
    }

    private companion object { const val TAG = "MediKioskAudio" }
}
