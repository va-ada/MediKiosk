package org.neural.medikiosk.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AirlineSeatFlat
import androidx.compose.material.icons.filled.Air
import androidx.compose.material.icons.filled.Bloodtype
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.Face
import androidx.compose.material.icons.filled.MonitorHeart
import androidx.compose.material.icons.filled.PregnantWoman
import androidx.compose.material.icons.filled.SentimentVeryDissatisfied
import androidx.compose.material.icons.filled.SupportAgent
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import org.neural.medikiosk.IntakeViewModel
import org.neural.medikiosk.LocalWipe
import org.neural.medikiosk.R
import org.neural.medikiosk.audio.LocalAudioPrompter
import org.neural.medikiosk.data.DeviceSettings
import org.neural.medikiosk.data.EmergencyRepository
import org.neural.medikiosk.emergency.Beacon
import org.neural.medikiosk.ui.theme.Red
import java.util.UUID

/** §2 reason_code → icon + hi/en label. */
private val REASONS: List<Triple<String, ImageVector, Int>> = listOf(
    Triple("chest_pain", Icons.Filled.MonitorHeart, R.string.reason_chest_pain),
    Triple("breathing", Icons.Filled.Air, R.string.reason_breathing),
    Triple("bleeding", Icons.Filled.Bloodtype, R.string.reason_bleeding),
    Triple("unconscious", Icons.Filled.AirlineSeatFlat, R.string.reason_unconscious),
    Triple("seizure", Icons.Filled.Bolt, R.string.reason_seizure),
    Triple("stroke_signs", Icons.Filled.Face, R.string.reason_stroke_signs),
    Triple("severe_pain", Icons.Filled.SentimentVeryDissatisfied, R.string.reason_severe_pain),
    Triple("pregnancy", Icons.Filled.PregnantWoman, R.string.reason_pregnancy),
    Triple("other", Icons.Filled.Warning, R.string.reason_other),
)

private enum class EmPhase { CHOOSE, BEACON, ACKNOWLEDGED }

/**
 * Emergency (reachable from every screen): pick what is happening → alarm to the server and the relay in
 * parallel (3 s caps, failures ignored) → full-screen "Help is coming" with the kiosk beacon (flash, tone,
 * torch). The beacon stops when a nurse acknowledges (`alert.updated` on the alerts channel) or staff hold
 * "Staff" for 3 s; the staff hand-off then wipes the kiosk (§10.9). Works with or without a session.
 */
@Composable
fun EmergencyScreen(vm: IntakeViewModel, settings: DeviceSettings, onBack: () -> Unit) {
    val context = LocalContext.current
    val wipe = LocalWipe.current
    val audio = LocalAudioPrompter.current
    val lang = LocalLang.current
    val scope = rememberCoroutineScope()
    val beacon = remember { Beacon(context) }
    val repo = remember { EmergencyRepository { vm.settings.value ?: settings } }
    var phase by rememberSaveable { mutableStateOf(EmPhase.CHOOSE) }
    var alertId by rememberSaveable { mutableStateOf<String?>(null) }
    var sent by remember { mutableStateOf<Pair<Boolean, Boolean>?>(null) }

    DisposableEffect(Unit) { onDispose { beacon.stop() } }
    BackHandler { if (phase == EmPhase.CHOOSE) onBack() }  // no way back out of a raised alarm except staff

    fun raise(reason: String) {
        val id = UUID.randomUUID().toString()
        alertId = id
        phase = EmPhase.BEACON
        audio.play("sys_help_coming", lang)
        beacon.start(scope, delayMs = 3500)  // let the patient hear the prompt first
        scope.launch { sent = repo.raise(id, reason, vm.session?.id) }
    }

    // A nurse acknowledging on /triage stops the beacon (the screen stays until staff hand over).
    DisposableEffect(alertId) {
        val id = alertId
        val close = if (id == null) null else repo.watch(id, isWanted = { phase == EmPhase.BEACON }) {
            scope.launch { if (phase == EmPhase.BEACON) { beacon.stop(); phase = EmPhase.ACKNOWLEDGED } }
        }
        onDispose { close?.invoke() }
    }

    if (phase == EmPhase.CHOOSE) {
        KioskScaffold(audioKey = null, speech = tr(R.string.em_what_happening), inactivity = false) {
            ScreenBody {
                Heading(tr(R.string.em_what_happening))
                Grid(REASONS, columns = 2) { (code, icon, label), m ->
                    IconTile(tr(label), icon, { raise(code) }, m)
                }
                BigOutlinedButton(tr(R.string.back), Icons.AutoMirrored.Filled.ArrowBack, onBack, Modifier.fillMaxWidth())
            }
        }
        return
    }

    // Full-screen help: flashing red/white at 1 Hz while the beacon runs.
    val view = LocalView.current
    DisposableEffect(Unit) { view.keepScreenOn = true; onDispose { view.keepScreenOn = false } }
    var flash by remember { mutableStateOf(false) }
    LaunchedEffect(phase) {
        while (phase == EmPhase.BEACON) { flash = !flash; delay(500) }
        flash = false
    }
    val bg = if (phase == EmPhase.BEACON && flash) Red else Color.White
    val fg = if (phase == EmPhase.BEACON && flash) Color.White else Color.Black
    Column(
        Modifier.fillMaxSize().background(bg).padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(20.dp, Alignment.CenterVertically),
    ) {
        Icon(Icons.Filled.SupportAgent, null, Modifier.size(120.dp), tint = fg)
        Text(tr(R.string.em_help_coming), fontSize = 40.sp, fontWeight = FontWeight.Bold, color = fg, textAlign = TextAlign.Center, lineHeight = 48.sp)
        Text(tr(R.string.em_stay_here), fontSize = 28.sp, color = fg, textAlign = TextAlign.Center)
        if (phase == EmPhase.ACKNOWLEDGED) {
            Text(tr(R.string.em_nurse_seen), fontSize = 26.sp, color = Color(0xFF1E8E6A), fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center)
        }
        sent?.let { (server, relay) ->
            Text(
                "${tr(R.string.em_sent_station)}: ${if (server || relay) "✓" else "✗"}   (server ${if (server) "✓" else "✗"} · relay ${if (relay) "✓" else "✗"})",
                fontSize = 20.sp, color = fg, textAlign = TextAlign.Center,
            )
        }
        ReplayAudioButton("sys_help_coming", modifier = Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(14.dp)))
        StaffHold(onDone = { beacon.stop(); wipe() })
    }
}

/** Staff-only release: hold for 3 seconds (a patient's tap does nothing). */
@Composable
private fun StaffHold(onDone: () -> Unit) {
    var holding by remember { mutableStateOf(false) }
    Surface(
        shape = RoundedCornerShape(16.dp),
        color = if (holding) MaterialTheme.colorScheme.secondary else Color.DarkGray,
        modifier = Modifier.fillMaxWidth().heightIn(min = 72.dp).pointerInput(Unit) {
            detectTapGestures(onPress = {
                holding = true
                val released = withTimeoutOrNull(3000) { tryAwaitRelease() }
                holding = false
                if (released == null) onDone()
            })
        },
    ) {
        Text(tr(R.string.em_staff_hold), color = Color.White, style = MaterialTheme.typography.labelLarge,
            textAlign = TextAlign.Center, modifier = Modifier.padding(20.dp))
    }
}
