package org.neural.medikiosk.ui.patientapp

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Campaign
import androidx.compose.material.icons.filled.HourglassTop
import androidx.compose.material.icons.filled.MeetingRoom
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import org.neural.medikiosk.IntakeViewModel
import org.neural.medikiosk.R
import org.neural.medikiosk.net.DisplayState
import org.neural.medikiosk.ui.departmentLabel
import org.neural.medikiosk.ui.theme.Green
import org.neural.medikiosk.ui.tr

const val STATUS_POLL_MS = 15_000L

/**
 * Patient-app live status (A14): polls `GET /api/display/state?department=` every 15 s and shows who is being
 * seen now and the patient's place in the `next` list (the board shows the next 5).
 */
@Composable
fun LiveStatusCard(vm: IntakeViewModel, modifier: Modifier = Modifier) {
    val token = vm.token ?: return
    val state by produceState<DisplayState?>(null, token.department) {
        while (true) {
            vm.repo.call { displayState(token.department) }.getOrNull()?.let { value = it }
            delay(STATUS_POLL_MS)
        }
    }
    val serving = state?.nowServing?.firstOrNull { it.display == token.display }
    val place = state?.next?.indexOf(token.display)?.takeIf { it >= 0 }?.plus(1)

    Card(
        modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        border = BorderStroke(3.dp, if (serving != null) Green else MaterialTheme.colorScheme.primary),
        colors = CardDefaults.cardColors(containerColor = if (serving != null) Green else MaterialTheme.colorScheme.surface),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(tr(R.string.pa_status_title), style = MaterialTheme.typography.titleLarge,
                color = if (serving != null) Color.White else MaterialTheme.colorScheme.onSurface)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(token.display, fontSize = 48.sp, fontWeight = FontWeight.Bold,
                    color = if (serving != null) Color.White else MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(12.dp))
                Text(tr(departmentLabel(token.department)), style = MaterialTheme.typography.bodyLarge,
                    color = if (serving != null) Color.White else MaterialTheme.colorScheme.onSurface)
            }
            when {
                state == null -> Text(tr(R.string.pa_status_loading), style = MaterialTheme.typography.bodyLarge)
                serving != null -> StatusLine(Icons.Filled.MeetingRoom, tr(R.string.pa_your_turn, serving.room ?: "—"), Color.White, big = true)
                place != null -> StatusLine(Icons.Filled.HourglassTop, tr(R.string.pa_place, place), MaterialTheme.colorScheme.onSurface, big = true)
                else -> StatusLine(Icons.Filled.HourglassTop, tr(R.string.pa_waiting), MaterialTheme.colorScheme.onSurface, big = false)
            }
            if (serving == null) {
                val now = state?.nowServing.orEmpty()
                StatusLine(Icons.Filled.Campaign,
                    if (now.isEmpty()) tr(R.string.pa_now_none) else tr(R.string.pa_now_serving, now.joinToString { it.display }),
                    MaterialTheme.colorScheme.onSurface, big = false)
            }
        }
    }
}

@Composable
private fun StatusLine(icon: androidx.compose.ui.graphics.vector.ImageVector, text: String, color: Color, big: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, null, Modifier.size(if (big) 36.dp else 28.dp), tint = color)
        Spacer(Modifier.width(10.dp))
        Text(text, color = color, style = if (big) MaterialTheme.typography.headlineMedium else MaterialTheme.typography.bodyLarge)
    }
}
