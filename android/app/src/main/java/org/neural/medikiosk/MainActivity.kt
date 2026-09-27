package org.neural.medikiosk

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import org.neural.medikiosk.data.DeviceSettings
import org.neural.medikiosk.data.SettingsRepository
import org.neural.medikiosk.ui.DeviceSettingsScreen
import org.neural.medikiosk.ui.theme.MediKioskTheme

/** Single activity (CLAUDE.md §8). A2 replaces the placeholder home with the kiosk navigation graph. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val repo = SettingsRepository(applicationContext)
        setContent {
            val settings by repo.settings.collectAsState(initial = DeviceSettings())
            var showSettings by remember { mutableStateOf(false) }
            val scope = rememberCoroutineScope()
            MediKioskTheme(highContrast = settings.highContrast, largeText = settings.largeText) {
                Surface(Modifier.fillMaxSize().safeDrawingPadding(), color = MaterialTheme.colorScheme.background) {
                    if (showSettings) {
                        DeviceSettingsScreen(settings, onSave = { scope.launch { repo.save(it); showSettings = false } },
                            onClose = { showSettings = false })
                    } else {
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                                Logo(onLongPress3s = { showSettings = true })
                                Text("${settings.deviceMode} · ${settings.deviceId}", style = MaterialTheme.typography.bodyMedium)
                            }
                        }
                    }
                }
            }
        }
    }
}

/** The app logo. Holding it for 3 seconds opens the hidden device settings. */
@Composable
fun Logo(onLongPress3s: () -> Unit, modifier: Modifier = Modifier) {
    Text(
        "MediKiosk",
        style = MaterialTheme.typography.displayLarge,
        color = MaterialTheme.colorScheme.primary,
        modifier = modifier.pointerInput(Unit) {
            detectTapGestures(onPress = {
                val released = withTimeoutOrNull(3000) { tryAwaitRelease() }
                if (released == null) onLongPress3s()
            })
        },
    )
}
