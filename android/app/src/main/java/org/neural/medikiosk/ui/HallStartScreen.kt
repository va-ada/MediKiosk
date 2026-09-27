package org.neural.medikiosk.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import org.neural.medikiosk.R

/**
 * Hall station start (device mode HALL): only "Scan your token slip" → resume → History → Read-back → Done
 * (no documents here); every patient ends with the automatic wipe back to this screen.
 */
@Composable
fun HallStartScreen(onScan: () -> Unit, onOpenSettings: () -> Unit) {
    KioskScaffold(audioKey = null, bilingual = true, inactivity = false,
        speech = "${trIn("hi", R.string.hall_scan)}. ${trIn("hi", R.string.hall_hint)}") {
        ScreenBody {
            Logo(onLongPress3s = onOpenSettings)
            Heading("${trIn("hi", R.string.hall_title)}\n${trIn("en", R.string.hall_title)}")
            BigButton("${trIn("hi", R.string.hall_scan)}\n${trIn("en", R.string.hall_scan)}", Icons.Filled.QrCodeScanner, onScan,
                Modifier.fillMaxWidth(), minHeight = 160.dp)
            Text("${trIn("hi", R.string.hall_hint)}\n${trIn("en", R.string.hall_hint)}", style = MaterialTheme.typography.bodyLarge,
                textAlign = TextAlign.Center)
        }
    }
}
