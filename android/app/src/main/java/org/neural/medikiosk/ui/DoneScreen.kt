package org.neural.medikiosk.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Home
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import org.neural.medikiosk.IntakeViewModel
import org.neural.medikiosk.LocalWipe
import org.neural.medikiosk.R
import org.neural.medikiosk.ui.theme.Green

const val DONE_SECONDS = 10

/** Done: thanks + token; after 10 s the kiosk wipes itself and returns to Start (§10.9). */
@Composable
fun DoneScreen(vm: IntakeViewModel, autoWipe: Boolean = true, statusCard: (@Composable () -> Unit)? = null) {
    val wipe = LocalWipe.current
    var left by remember { mutableIntStateOf(DONE_SECONDS) }
    BackHandler { }  // nothing to go back to
    LaunchedEffect(autoWipe) {
        if (!autoWipe) return@LaunchedEffect  // patient app: keep showing the live status until they finish
        while (left > 0) { delay(1000); left -= 1 }
        wipe()
    }
    KioskScaffold(audioKey = "sys_thanks", inactivity = false) {
        ScreenBody {
            Icon(Icons.Filled.CheckCircle, null, Modifier.size(120.dp), tint = Green)
            Heading(tr(R.string.done_thanks))
            if (statusCard != null) statusCard() else vm.token?.let { TokenBadge(it) }
            Text(tr(R.string.done_wait), style = MaterialTheme.typography.bodyLarge, textAlign = TextAlign.Center)
            if (autoWipe) Text(tr(R.string.done_clearing, left), style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center)
            BigOutlinedButton(tr(R.string.done_finish_now), Icons.Filled.Home, wipe, Modifier.fillMaxWidth())
        }
    }
}
