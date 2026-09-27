package org.neural.medikiosk.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.neural.medikiosk.data.DeviceSettings
import org.neural.medikiosk.net.ApiClient
import org.neural.medikiosk.net.DeviceMode
import org.neural.medikiosk.ui.theme.Green
import org.neural.medikiosk.ui.theme.MinTouch
import org.neural.medikiosk.ui.theme.Red

/** Hidden device settings (long-press the logo for 3 s). Staff-only; no patient data here. */
@Composable
fun DeviceSettingsScreen(initial: DeviceSettings, onSave: (DeviceSettings) -> Unit, onClose: () -> Unit, onAccessibility: () -> Unit) {
    // Draft of the connection/mode fields; accessibility toggles live in SettingsScreen (saved at once there).
    var s by remember { mutableStateOf(initial) }
    var status by remember { mutableStateOf<Pair<Boolean, String>?>(null) }
    val scope = rememberCoroutineScope()

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Device settings", style = MaterialTheme.typography.headlineMedium)
        OutlinedTextField(s.serverUrl, { s = s.copy(serverUrl = it) }, label = { Text("Server URL") },
            singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), modifier = Modifier.fillMaxWidth())
        OutlinedTextField(s.relayUrl, { s = s.copy(relayUrl = it) }, label = { Text("Alarm relay URL") },
            singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), modifier = Modifier.fillMaxWidth())
        OutlinedTextField(s.deviceId, { s = s.copy(deviceId = it) }, label = { Text("Device ID (KIOSK-01, HALL-01, APP-FOLD)") },
            singleLine = true, modifier = Modifier.fillMaxWidth())

        Text("Device mode", style = MaterialTheme.typography.titleLarge)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(DeviceMode.KIOSK to "Kiosk", DeviceMode.HALL to "Hall", DeviceMode.PATIENT_APP to "Patient app").forEach { (m, label) ->
                FilterChip(selected = s.deviceMode == m, onClick = { s = s.copy(deviceMode = m) }, label = { Text(label) },
                    modifier = Modifier.heightIn(min = MinTouch))
            }
        }
        Text("Default language", style = MaterialTheme.typography.titleLarge)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("hi" to "हिंदी", "en" to "English").forEach { (code, label) ->
                FilterChip(selected = s.defaultLanguage == code, onClick = { s = s.copy(defaultLanguage = code) },
                    label = { Text(label) }, modifier = Modifier.heightIn(min = MinTouch))
            }
        }
        OutlinedButton(onClick = onAccessibility, modifier = Modifier.fillMaxWidth().heightIn(min = MinTouch)) {
            Text("Accessibility: large text, high contrast, slower prompts, handset mode")
        }

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedButton(onClick = {
                status = null
                scope.launch {
                    status = runCatching { ApiClient.api(s.serverUrl, s.deviceId, 5).health() }
                        .fold({ true to "Connected · v${it.version}" }, { false to "Not reachable (${ApiClient.errorCode(it)})" })
                }
            }, modifier = Modifier.heightIn(min = MinTouch)) { Text("Test connection") }
            status?.let { (ok, msg) ->
                AssistChip(onClick = {}, label = { Text(msg) },
                    colors = AssistChipDefaults.assistChipColors(containerColor = if (ok) Green else Red, labelColor = Color.White))
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(onClick = { onSave(s) }, modifier = Modifier.heightIn(min = MinTouch)) { Text("Save") }
            OutlinedButton(onClick = onClose, modifier = Modifier.heightIn(min = MinTouch)) { Text("Close") }
        }
    }
}
