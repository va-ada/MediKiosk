package org.neural.medikiosk.ui

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.MediaRecorder
import android.os.Build
import android.os.SystemClock
import android.util.Log
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Psychology
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import org.neural.medikiosk.R
import org.neural.medikiosk.audio.LocalAudioPrompter
import org.neural.medikiosk.ui.theme.Red
import java.io.File
import java.util.UUID

/** Voice answer states shown on the mic. */
enum class VoicePhase { IDLE, RECORDING, UPLOADING, UNDERSTANDING }

/** MediaRecorder → MPEG_4/AAC, 16 kHz mono, into the cache dir (wiped with the session). */
private class Recorder(private val context: Context) {
    private var rec: MediaRecorder? = null
    var file: File? = null
    var startedAt = 0L

    fun start(): Boolean {
        val f = File(context.cacheDir, "voice_${UUID.randomUUID()}.m4a")
        @Suppress("DEPRECATION")
        val r = if (Build.VERSION.SDK_INT >= 31) MediaRecorder(context) else MediaRecorder()
        return runCatching {
            r.setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
            r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            r.setAudioSamplingRate(16_000)
            r.setAudioChannels(1)
            r.setAudioEncodingBitRate(64_000)
            r.setOutputFile(f.path)
            r.prepare()
            r.start()
            rec = r; file = f; startedAt = SystemClock.elapsedRealtime()
            true
        }.getOrElse {
            Log.w("MediKiosk", "recorder start failed: ${it.message}")
            r.release(); f.delete(); false
        }
    }

    /** Stop and return the clip (null if too short or broken — the file is deleted then). */
    fun stop(): File? {
        val r = rec ?: return null
        val ok = runCatching { r.stop() }.isSuccess
        r.release(); rec = null
        val f = file; file = null
        val longEnough = SystemClock.elapsedRealtime() - startedAt >= 500
        return if (ok && longEnough) f else { f?.delete(); null }
    }

    fun cancel() { runCatching { rec?.stop() }; rec?.release(); rec = null; file?.delete(); file = null }
}

/**
 * Large hold-to-talk mic (≥ 120 dp). Press = record, release = [onRecorded] with the clip (the caller uploads
 * and deletes it). Asks for RECORD_AUDIO the first time. [debugClip] (debug builds only) replaces the recording.
 */
@Composable
fun MicButton(phase: VoicePhase, enabled: Boolean, onRecorded: (File) -> Unit, debugClip: File? = null, onPhase: (VoicePhase) -> Unit) {
    val context = LocalContext.current
    val audio = LocalAudioPrompter.current
    var granted by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
    }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted = it }
    val recorder = remember { Recorder(context) }
    var tooShort by remember { mutableStateOf(false) }
    DisposableEffect(Unit) { onDispose { recorder.cancel() } }

    val busy = phase == VoicePhase.UPLOADING || phase == VoicePhase.UNDERSTANDING
    val color = when (phase) {
        VoicePhase.RECORDING -> Red
        VoicePhase.IDLE -> MaterialTheme.colorScheme.primary
        else -> MaterialTheme.colorScheme.outline
    }
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(
            Modifier.size(128.dp).clip(CircleShape).background(color).pointerInput(enabled, granted, busy) {
                detectTapGestures(onPress = {
                    if (!enabled || busy) return@detectTapGestures
                    if (!granted) { ask.launch(Manifest.permission.RECORD_AUDIO); return@detectTapGestures }
                    audio.stop()  // don't record the prompt
                    tooShort = false
                    val started = recorder.start()
                    if (!started && debugClip == null) return@detectTapGestures
                    onPhase(VoicePhase.RECORDING)
                    tryAwaitRelease()
                    val clip = if (started) recorder.stop() else null
                    val use = debugClip?.let { dbg ->
                        clip?.delete()
                        File(context.cacheDir, "voice_debug_${UUID.randomUUID()}.m4a").also { dbg.copyTo(it) }
                            .also { Log.i("MediKiosk", "DEBUG voice clip used instead of the recording: ${dbg.name}") }
                    } ?: clip
                    if (use == null) { tooShort = true; onPhase(VoicePhase.IDLE) } else onRecorded(use)
                })
            },
            contentAlignment = Alignment.Center,
        ) {
            when (phase) {
                VoicePhase.IDLE, VoicePhase.RECORDING -> Icon(Icons.Filled.Mic, null, Modifier.size(72.dp), tint = Color.White)
                VoicePhase.UPLOADING -> Icon(Icons.Filled.CloudUpload, null, Modifier.size(64.dp), tint = Color.White)
                VoicePhase.UNDERSTANDING -> Icon(Icons.Filled.Psychology, null, Modifier.size(64.dp), tint = Color.White)
            }
            if (busy) CircularProgressIndicator(Modifier.size(120.dp), color = Color.White)
        }
        Text(
            tr(when {
                tooShort -> R.string.mic_too_short
                phase == VoicePhase.RECORDING -> R.string.mic_recording
                phase == VoicePhase.UPLOADING -> R.string.mic_uploading
                phase == VoicePhase.UNDERSTANDING -> R.string.mic_understanding
                !granted -> R.string.mic_allow
                else -> R.string.mic_hold
            }),
            style = MaterialTheme.typography.titleLarge,
            textAlign = TextAlign.Center,
        )
    }
}
