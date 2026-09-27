package org.neural.medikiosk.ui.answers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import org.neural.medikiosk.LocalActivityPing
import org.neural.medikiosk.R
import org.neural.medikiosk.net.Choice
import org.neural.medikiosk.ui.BigButton
import org.neural.medikiosk.ui.tr

/**
 * Free text (e.g. medicine names): the question's tap choices ("no medicines", "I don't remember") first,
 * then a text field (system keyboard, whose own mic also works). The hold-to-talk mic sits above every
 * question (HistoryScreen), so it is not repeated here.
 */
@Composable
fun FreeAnswer(questionId: String, choices: List<Choice>, enabled: Boolean, onAnswer: (JsonElement) -> Unit) {
    var text by rememberSaveable(questionId) { mutableStateOf("") }
    val ping = LocalActivityPing.current
    val keyboard = LocalSoftwareKeyboardController.current
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (choices.isNotEmpty()) ChoiceAnswer(choices, enabled) { keyboard?.hide(); onAnswer(it) }
        Text(tr(R.string.answer_or_write), style = MaterialTheme.typography.bodyMedium)
        OutlinedTextField(
            value = text,
            onValueChange = { ping(); if (it.length <= 500) text = it },
            textStyle = MaterialTheme.typography.bodyLarge,
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
            modifier = Modifier.fillMaxWidth().heightIn(min = 120.dp),
        )
        BigButton(tr(R.string.answer_done), Icons.Filled.Check, { keyboard?.hide(); onAnswer(JsonPrimitive(text.trim())) },
            Modifier.fillMaxWidth(), enabled = enabled && text.isNotBlank())
    }
}
