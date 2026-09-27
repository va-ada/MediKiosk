package org.neural.medikiosk.ui.patientapp

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.LocalHospital
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material.icons.filled.Translate
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.neural.medikiosk.R
import org.neural.medikiosk.net.ApiClient
import org.neural.medikiosk.ui.BigButton
import org.neural.medikiosk.ui.BigOutlinedButton
import org.neural.medikiosk.ui.ErrorCard
import org.neural.medikiosk.ui.Heading
import org.neural.medikiosk.ui.KioskScaffold
import org.neural.medikiosk.ui.LocalLang
import org.neural.medikiosk.ui.Logo
import org.neural.medikiosk.ui.QrCamera
import org.neural.medikiosk.ui.ScreenBody
import org.neural.medikiosk.ui.theme.MinTouch
import org.neural.medikiosk.ui.tr

/** The hospital check-in QR at the entrance: `{"hospital": "DEMO"}`. */
fun hospitalFromQr(text: String): String? = runCatching {
    ApiClient.json.parseToJsonElement(text).jsonObject["hospital"]?.jsonPrimitive?.content
}.getOrNull()?.takeIf { it.isNotBlank() }

/**
 * Patient app home (device mode PATIENT_APP, e.g. the Z Fold): choose a language, then "Check in at hospital"
 * by scanning the entrance QR (`{"hospital":"DEMO"}`) or "Demo check-in" → the normal Identify flow.
 */
@Composable
fun PatientHomeScreen(onLanguage: (String) -> Unit, onCheckIn: () -> Unit, onOpenSettings: () -> Unit) {
    val context = LocalContext.current
    val lang = LocalLang.current
    var scanning by rememberSaveable { mutableStateOf(false) }
    var badCode by remember { mutableStateOf(false) }
    var granted by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted = it; scanning = it }

    KioskScaffold(audioKey = "sys_welcome", inactivity = false) {
        ScreenBody {
            Logo(onLongPress3s = onOpenSettings)
            Heading(tr(R.string.pa_home_title))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                listOf("hi" to "हिंदी", "en" to "English").forEach { (code, label) ->
                    FilterChip(selected = lang == code, onClick = { onLanguage(code) },
                        label = { Text(label, style = MaterialTheme.typography.titleLarge) },
                        leadingIcon = { Icon(Icons.Filled.Translate, null) }, modifier = Modifier.heightIn(min = MinTouch))
                }
            }
            if (badCode) ErrorCard("validation_error")
            if (scanning && granted) {
                Text(tr(R.string.pa_scan_hint), style = MaterialTheme.typography.bodyLarge, textAlign = TextAlign.Center)
                QrCamera(onText = { text -> if (hospitalFromQr(text) != null) { scanning = false; onCheckIn() } else badCode = true },
                    modifier = Modifier.fillMaxWidth().aspectRatio(1f))
            } else {
                BigButton(tr(R.string.pa_scan), Icons.Filled.QrCodeScanner,
                    { if (granted) scanning = true else ask.launch(Manifest.permission.CAMERA) }, Modifier.fillMaxWidth(), minHeight = 110.dp)
            }
            BigOutlinedButton(tr(R.string.pa_demo_checkin), Icons.Filled.LocalHospital, onCheckIn, Modifier.fillMaxWidth())
        }
    }
}
