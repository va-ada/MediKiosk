package org.neural.medikiosk.ui.answers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import org.neural.medikiosk.R
import org.neural.medikiosk.net.Choice
import org.neural.medikiosk.ui.BigButton
import org.neural.medikiosk.ui.DigitDisplay
import org.neural.medikiosk.ui.Grid
import org.neural.medikiosk.ui.NumericKeypad
import org.neural.medikiosk.ui.tr
import org.neural.medikiosk.ui.theme.MinTouch

/** Quick-pick tiles (the question's own choices, e.g. "a few months" = 90 days) above the keypad. */
@Composable
private fun QuickPicks(choices: List<Choice>, enabled: Boolean, onAnswer: (JsonElement) -> Unit) {
    if (choices.isEmpty()) return
    Text(tr(R.string.answer_quick_pick), style = MaterialTheme.typography.bodyMedium)
    ChoiceAnswer(choices, enabled, onAnswer)
    Text(tr(R.string.answer_or_type), style = MaterialTheme.typography.bodyMedium)
}

/** Whole number on a big keypad (e.g. hours of sleep). */
@Composable
fun NumberAnswer(questionId: String, choices: List<Choice>, enabled: Boolean, onAnswer: (JsonElement) -> Unit) {
    var digits by rememberSaveable(questionId) { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        QuickPicks(choices, enabled, onAnswer)
        DigitDisplay(digits, "0")
        NumericKeypad({ if (digits.length < 3) digits = (digits + it).trimStart('0').ifEmpty { "0" } }, { digits = digits.dropLast(1) })
        BigButton(tr(R.string.answer_done), Icons.Filled.Check, { onAnswer(JsonPrimitive(digits.toInt())) },
            Modifier.fillMaxWidth(), enabled = enabled && digits.isNotEmpty())
    }
}

/** Duration units → days (slot type `duration_days`). */
private val UNITS = listOf(
    Triple("days", R.string.unit_days, 1),
    Triple("weeks", R.string.unit_weeks, 7),
    Triple("months", R.string.unit_months, 30),
    Triple("years", R.string.unit_years, 365),
)

/** "How long?": number keypad + unit chips (days / weeks / months / years), sent as days. */
@Composable
fun DurationAnswer(questionId: String, choices: List<Choice>, enabled: Boolean, onAnswer: (JsonElement) -> Unit) {
    var digits by rememberSaveable(questionId) { mutableStateOf("") }
    var unit by rememberSaveable(questionId) { mutableStateOf("days") }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        QuickPicks(choices, enabled, onAnswer)
        DigitDisplay(if (digits.isEmpty()) "" else "$digits ${tr(UNITS.first { it.first == unit }.second)}", "0")
        Grid(UNITS, columns = 2, spacing = 8.dp) { (code, label, _), m ->
            FilterChip(selected = unit == code, onClick = { unit = code },
                label = { Text(tr(label), style = MaterialTheme.typography.titleLarge) }, modifier = m.heightIn(min = MinTouch))
        }
        NumericKeypad({ if (digits.length < 3) digits = (digits + it).trimStart('0').ifEmpty { "0" } }, { digits = digits.dropLast(1) })
        BigButton(tr(R.string.answer_done), Icons.Filled.Check, {
            val days = digits.toInt() * UNITS.first { it.first == unit }.third
            onAnswer(JsonPrimitive(days.coerceAtMost(36500)))
        }, Modifier.fillMaxWidth(), enabled = enabled && digits.isNotEmpty())
    }
}
