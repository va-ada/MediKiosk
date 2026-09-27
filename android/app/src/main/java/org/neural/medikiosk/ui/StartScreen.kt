package org.neural.medikiosk.ui

import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material.icons.filled.Translate
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.withTimeoutOrNull
import org.neural.medikiosk.R

/** Start: two big language tiles (हिंदी / English). Long-press the logo 3 s → hidden device settings. */
@Composable
fun StartScreen(onLanguage: (String) -> Unit, onOpenSettings: () -> Unit, onResume: () -> Unit) {
    KioskScaffold(audioKey = "sys_welcome", bilingual = true, inactivity = false) {
        Column(
            Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState()).padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(24.dp, Alignment.CenterVertically),
        ) {
            Logo(onLongPress3s = onOpenSettings)
            Text(
                "${trIn("hi", R.string.choose_language)}\n${trIn("en", R.string.choose_language)}",
                style = MaterialTheme.typography.headlineMedium,
                textAlign = TextAlign.Center,
            )
            BigButton("हिंदी", Icons.Filled.Translate, { onLanguage("hi") }, Modifier.fillMaxWidth(), minHeight = 120.dp)
            BigButton("English", Icons.Filled.Translate, { onLanguage("en") }, Modifier.fillMaxWidth(), minHeight = 120.dp)
            BigOutlinedButton("${trIn("hi", R.string.resume_title)}\n${trIn("en", R.string.resume_title)}", Icons.Filled.QrCodeScanner,
                onResume, Modifier.fillMaxWidth())
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
        modifier = modifier.heightIn(min = 72.dp).pointerInput(Unit) {
            detectTapGestures(onPress = {
                val released = withTimeoutOrNull(3000) { tryAwaitRelease() }
                if (released == null) onLongPress3s()
            })
        },
    )
}
