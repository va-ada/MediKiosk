package org.neural.medikiosk

import android.app.ActivityManager
import android.content.Context
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.neural.medikiosk.audio.LocalAudioPrompter
import org.neural.medikiosk.audio.AssetAudioPrompter
import org.neural.medikiosk.navigation.KioskNavHost
import org.neural.medikiosk.net.DeviceMode
import org.neural.medikiosk.ui.theme.MediKioskTheme

/** Single activity (CLAUDE.md §8): theme + audio + the kiosk navigation graph. */
class MainActivity : ComponentActivity() {
    private val vm: IntakeViewModel by viewModels()
    private val audio by lazy { AssetAudioPrompter(this) }

    override fun onDestroy() {
        audio.release()
        super.onDestroy()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val settings by vm.settings.collectAsStateWithLifecycle()
            val s = settings ?: return@setContent  // wait for DataStore (start screen depends on the device mode)
            LaunchedEffect(s.deviceMode) { applyKioskLock(s.deviceMode == DeviceMode.KIOSK) }
            LaunchedEffect(s.handsetMode, s.slowPrompts) { audio.handset = s.handsetMode; audio.slow = s.slowPrompts }
            CompositionLocalProvider(LocalAudioPrompter provides audio) {
                MediKioskTheme(highContrast = s.highContrast, largeText = s.largeText) {
                    Surface(Modifier.fillMaxSize().safeDrawingPadding(), color = MaterialTheme.colorScheme.background) {
                        key(s.deviceMode) { KioskNavHost(vm, s) }  // a mode change rebuilds the graph (new start screen)
                    }
                }
            }
        }
    }

    /**
     * KIOSK mode pins the app (startLockTask). Without device-owner provisioning Android shows its
     * screen-pinning confirmation; staff unpin with Back + Overview held together (see README).
     */
    private fun applyKioskLock(lock: Boolean) {
        val am = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val locked = am.lockTaskModeState != ActivityManager.LOCK_TASK_MODE_NONE
        runCatching {
            if (lock && !locked) startLockTask()
            if (!lock && locked) stopLockTask()
        }.onFailure { Log.w("MediKiosk", "lock task: ${it.message}") }
    }
}
