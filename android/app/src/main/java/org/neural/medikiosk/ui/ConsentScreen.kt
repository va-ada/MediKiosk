package org.neural.medikiosk.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.Badge
import androidx.compose.material.icons.filled.EditNote
import androidx.compose.material.icons.filled.LocalHospital
import androidx.compose.material.icons.filled.MedicalServices
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.Public
import androidx.compose.material.icons.filled.Store
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.neural.medikiosk.IntakeViewModel
import org.neural.medikiosk.R
import org.neural.medikiosk.audio.LocalAudioPrompter
import org.neural.medikiosk.data.errorCode
import org.neural.medikiosk.net.ConsentRequest
import org.neural.medikiosk.ui.theme.MinTouch

/**
 * Consent (journey step 2b): audio explanation (`sys_consent`), four toggles (default ON; ABHA link only when the
 * patient has ABHA) and one check question. A wrong answer replays the explanation once; the second attempt
 * proceeds with `check_passed = false`.
 */
@Composable
fun ConsentScreen(vm: IntakeViewModel, onDone: () -> Unit, onBack: () -> Unit) {
    val session = vm.session ?: return
    val hasAbha = vm.patient?.abhaNumber != null
    var capture by rememberSaveable { mutableStateOf(true) }
    var scan by rememberSaveable { mutableStateOf(true) }
    var share by rememberSaveable { mutableStateOf(true) }
    var linkAbha by rememberSaveable { mutableStateOf(hasAbha) }
    var checking by rememberSaveable { mutableStateOf(false) }
    var wrongTries by rememberSaveable { mutableIntStateOf(0) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val audio = LocalAudioPrompter.current
    val lang = LocalLang.current
    BackHandler { if (checking) checking = false else onBack() }

    fun send(passed: Boolean) {
        busy = true; error = null
        scope.launch {
            val r = vm.repo.call { consent(session.id, ConsentRequest(capture, scan, share, hasAbha && linkAbha, passed)) }
            busy = false
            r.onSuccess { onDone() }
            error = r.errorCode()
        }
    }

    KioskScaffold(audioKey = "sys_consent") {
        ScreenBody {
            if (!checking) {
                Heading(tr(R.string.consent_title))
                Text(tr(R.string.consent_explain), style = MaterialTheme.typography.bodyLarge)
                ConsentToggle(tr(R.string.consent_capture), Icons.Filled.EditNote, capture) { capture = it }
                ConsentToggle(tr(R.string.consent_scan), Icons.Filled.PhotoCamera, scan) { scan = it }
                ConsentToggle(tr(R.string.consent_share), Icons.Filled.LocalHospital, share) { share = it }
                if (hasAbha) ConsentToggle(tr(R.string.consent_link_abha), Icons.Filled.Badge, linkAbha) { linkAbha = it }
                NavRow(onBack, tr(R.string.next), enabled = true) { checking = true }
            } else {
                Heading(tr(R.string.consent_check_q))
                if (wrongTries > 0) {
                    Text(tr(R.string.consent_check_wrong), style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.error)
                }
                ErrorCard(error)
                if (busy) CircularProgressIndicator()
                val options = listOf(
                    Triple(true, R.string.consent_opt_doctor, Icons.Filled.MedicalServices),
                    Triple(false, R.string.consent_opt_internet, Icons.Filled.Public),
                    Triple(false, R.string.consent_opt_companies, Icons.Filled.Store),
                )
                options.forEach { (correct, label, icon) ->
                    IconTile(tr(label), icon, {
                        if (busy) return@IconTile
                        when {
                            correct -> send(true)
                            wrongTries == 0 -> { wrongTries = 1; audio.play("sys_consent", lang) }
                            else -> send(false)
                        }
                    }, Modifier.fillMaxWidth())
                }
                if (error != null) {
                    BigButton(tr(R.string.try_again), Icons.AutoMirrored.Filled.ArrowForward, { send(wrongTries == 0) }, Modifier.fillMaxWidth())
                }
            }
        }
    }
}

@Composable
private fun ConsentToggle(label: String, icon: ImageVector, checked: Boolean, onChange: (Boolean) -> Unit) {
    Card(
        onClick = { onChange(!checked) },
        modifier = Modifier.fillMaxWidth().heightIn(min = MinTouch + 16.dp),
        shape = RoundedCornerShape(12.dp),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(icon, contentDescription = null, modifier = Modifier.size(36.dp), tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(4.dp))
            Text(label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
            Switch(checked = checked, onCheckedChange = onChange)
        }
    }
}
