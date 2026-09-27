package org.neural.medikiosk

import android.os.SystemClock
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.TouchApp
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import org.neural.medikiosk.audio.LocalAudioPrompter
import org.neural.medikiosk.ui.BigButton
import org.neural.medikiosk.ui.LocalLang
import org.neural.medikiosk.ui.tr

/** Wipe the patient and return to the start screen (§10.9). Provided by the nav host. */
val LocalWipe = staticCompositionLocalOf<() -> Unit> { {} }

/** Report activity that isn't a touch on our window (typing on the soft keyboard). */
val LocalActivityPing = staticCompositionLocalOf<() -> Unit> { {} }

/** False in the patient app: it is the patient's own phone, which may sit on the token screen for a long time. */
val LocalInactivityEnabled = staticCompositionLocalOf { true }

const val IDLE_MS = 60_000L
const val COUNTDOWN_S = 30

/**
 * Inactivity on intake screens: 60 s without a touch → `sys_still_there` + a 30 s countdown overlay →
 * wipe to Start. Any touch (or keyboard typing via [LocalActivityPing]) resets the timer.
 */
@Composable
fun InactivityWatcher(enabled: Boolean, content: @Composable () -> Unit) {
    if (!enabled || !LocalInactivityEnabled.current) return content()
    val wipe = LocalWipe.current
    val audio = LocalAudioPrompter.current
    val lang = LocalLang.current
    var lastActivity by remember { mutableLongStateOf(SystemClock.elapsedRealtime()) }
    var countdown by remember { mutableStateOf<Int?>(null) }
    val ping = { lastActivity = SystemClock.elapsedRealtime(); countdown = null }

    LaunchedEffect(lastActivity) {
        delay(IDLE_MS)
        audio.play("sys_still_there", lang)
        for (s in COUNTDOWN_S downTo 1) {
            countdown = s
            delay(1000)
        }
        countdown = null
        wipe()
    }

    Box(
        Modifier.fillMaxSize().pointerInput(Unit) {
            awaitPointerEventScope {
                while (true) {
                    awaitPointerEvent(PointerEventPass.Initial)
                    ping()
                }
            }
        },
    ) {
        CompositionLocalProvider(LocalActivityPing provides ping) { content() }
        countdown?.let { StillThereOverlay(it, ping) }
    }
}

@Composable
private fun StillThereOverlay(secondsLeft: Int, onContinue: () -> Unit) {
    Column(
        Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background.copy(alpha = 0.97f))
            .pointerInput(Unit) { detectTapGestures { onContinue() } }  // swallow taps: never hit an answer underneath
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(24.dp, Alignment.CenterVertically),
    ) {
        Text(tr(R.string.still_there), style = MaterialTheme.typography.headlineLarge, textAlign = TextAlign.Center)
        Text("$secondsLeft", fontSize = 96.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.error)
        Text(tr(R.string.still_there_hint), style = MaterialTheme.typography.bodyLarge, textAlign = TextAlign.Center)
        BigButton(tr(R.string.still_there_continue), Icons.Filled.TouchApp, onContinue, Modifier.fillMaxWidth(), minHeight = 110.dp)
    }
}
