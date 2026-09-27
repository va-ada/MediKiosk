package org.neural.medikiosk.ui.answers

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.SentimentDissatisfied
import androidx.compose.material.icons.filled.SentimentNeutral
import androidx.compose.material.icons.filled.SentimentSatisfied
import androidx.compose.material.icons.filled.SentimentVeryDissatisfied
import androidx.compose.material.icons.filled.SentimentVerySatisfied
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import org.neural.medikiosk.R
import org.neural.medikiosk.ui.Grid
import org.neural.medikiosk.ui.tr
import org.neural.medikiosk.ui.theme.Green
import org.neural.medikiosk.ui.theme.Red

/** 0–10 with faces (0 = no pain … 10 = worst); colour goes green → red. Words at both ends. */
@Composable
fun ScaleAnswer(enabled: Boolean, onAnswer: (JsonElement) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("0 = ${tr(R.string.scale_none)}   ·   10 = ${tr(R.string.scale_worst)}", style = MaterialTheme.typography.bodyLarge)
        Grid((0..10).toList(), columns = 4, spacing = 8.dp) { n, m ->
            val face = when (n) {
                0, 1 -> Icons.Filled.SentimentVerySatisfied
                2, 3 -> Icons.Filled.SentimentSatisfied
                4, 5 -> Icons.Filled.SentimentNeutral
                6, 7, 8 -> Icons.Filled.SentimentDissatisfied
                else -> Icons.Filled.SentimentVeryDissatisfied
            }
            val color = lerp(Green, Red, n / 10f)
            Card(
                onClick = { if (enabled) onAnswer(JsonPrimitive(n)) },
                modifier = m.heightIn(min = 88.dp),
                shape = RoundedCornerShape(14.dp),
                border = BorderStroke(3.dp, color),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            ) {
                Column(Modifier.fillMaxWidth().padding(6.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(face, contentDescription = null, tint = color, modifier = Modifier.size(36.dp))
                    Text("$n", style = MaterialTheme.typography.headlineMedium)
                }
            }
        }
    }
}
