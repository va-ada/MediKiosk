package org.neural.medikiosk.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.TouchApp
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import kotlinx.serialization.json.JsonElement
import org.neural.medikiosk.R
import org.neural.medikiosk.audio.LocalAudioPrompter
import org.neural.medikiosk.net.Choice
import org.neural.medikiosk.net.Question
import org.neural.medikiosk.ui.answers.ChoiceAnswer

/**
 * "Did you mean…?" after an uncertain voice answer (`fallback_choices` non-empty): plays `sys_did_you_mean`,
 * shows what was heard and the question's choices as tap buttons (→ `POST answers`, source tap).
 * Shown inside the history screen (same scaffold), so Emergency / Need help / Listen again stay available.
 */
@Composable
fun DidYouMeanScreen(
    question: Question,
    heard: String?,
    choices: List<Choice>,
    enabled: Boolean,
    onChoice: (JsonElement) -> Unit,
    onSpeakAgain: () -> Unit,
    onTapInstead: () -> Unit,
) {
    val audio = LocalAudioPrompter.current
    val lang = LocalLang.current
    LaunchedEffect(question.id, heard) { audio.play("sys_did_you_mean", lang) }
    Heading(tr(R.string.dym_title))
    Text(question.text, style = MaterialTheme.typography.bodyLarge, textAlign = TextAlign.Center)
    if (!heard.isNullOrBlank()) {
        Text(tr(R.string.dym_heard, heard), style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center)
    }
    ChoiceAnswer(choices, enabled, onChoice)
    BigOutlinedButton(tr(R.string.dym_speak_again), Icons.Filled.Mic, onSpeakAgain, Modifier.fillMaxWidth(), enabled = enabled)
    BigOutlinedButton(tr(R.string.dym_tap_instead), Icons.Filled.TouchApp, onTapInstead, Modifier.fillMaxWidth(), enabled = enabled)
}
