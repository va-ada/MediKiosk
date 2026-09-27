package org.neural.medikiosk.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.neural.medikiosk.audio.LocalAudioPrompter
import org.neural.medikiosk.data.DeviceSettings
import org.neural.medikiosk.ui.theme.MinTouch

/**
 * Staff-facing accessibility settings (reached from the hidden device settings). Each toggle is saved and
 * applied at once, so staff see the effect immediately:
 * large text (font scale ×1.3), high-contrast theme, slower prompts (playback 0.85×), handset mode (earpiece).
 */
@Composable
fun SettingsScreen(settings: DeviceSettings, onChange: (DeviceSettings) -> Unit, onClose: () -> Unit) {
    val audio = LocalAudioPrompter.current
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Accessibility", style = MaterialTheme.typography.headlineMedium)
        Toggle("Large text", "All text 1.3× bigger", settings.largeText) { onChange(settings.copy(largeText = it)) }
        Toggle("High contrast", "Black background, white text, yellow buttons", settings.highContrast) { onChange(settings.copy(highContrast = it)) }
        Toggle("Slower prompts", "Audio prompts play at 0.85× speed", settings.slowPrompts) { onChange(settings.copy(slowPrompts = it)) }
        Toggle("Handset mode", "Prompts come from the earpiece — the patient holds the phone to the ear", settings.handsetMode) {
            onChange(settings.copy(handsetMode = it))
        }
        Card(
            Modifier.fillMaxWidth(),
            border = BorderStroke(2.dp, MaterialTheme.colorScheme.primary),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        ) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Preview", style = MaterialTheme.typography.titleLarge)
                Text("सबसे ज़्यादा दर्द किस जोड़ में है?", style = MaterialTheme.typography.headlineMedium)
                Text("Which joint hurts the most?", style = MaterialTheme.typography.bodyLarge)
                BigButton("घुटना / Knee", contentIcon("knee"), {}, Modifier.fillMaxWidth())
                BigOutlinedButton("Play a prompt", Icons.AutoMirrored.Filled.VolumeUp, { audio.play("jp_site", "hi") }, Modifier.fillMaxWidth())
            }
        }
        BigOutlinedButton("Back", Icons.AutoMirrored.Filled.ArrowBack, onClose, Modifier.fillMaxWidth())
    }
}

@Composable
private fun Toggle(label: String, hint: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Card(
        onClick = { onChange(!checked) },
        modifier = Modifier.fillMaxWidth().heightIn(min = MinTouch + 16.dp),
        shape = RoundedCornerShape(12.dp),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(label, style = MaterialTheme.typography.titleLarge)
                Text(hint, style = MaterialTheme.typography.bodyMedium)
            }
            Switch(checked = checked, onCheckedChange = onChange)
        }
    }
}
