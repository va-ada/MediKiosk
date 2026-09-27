package org.neural.medikiosk.ui.answers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import org.neural.medikiosk.R
import org.neural.medikiosk.net.Choice
import org.neural.medikiosk.ui.BigButton
import org.neural.medikiosk.ui.Grid
import org.neural.medikiosk.ui.IconTile
import org.neural.medikiosk.ui.contentIcon
import org.neural.medikiosk.ui.tr

/** Choice values that mean "none of these" / "don't know" and so exclude every other pick. */
private val EXCLUSIVE = setOf("none", "dont_know", "not_sure")

fun Choice.key(): String = (value as? JsonPrimitive)?.content ?: value.toString()

/** Single choice: icon cards with labels; one tap answers. */
@Composable
fun ChoiceAnswer(choices: List<Choice>, enabled: Boolean, onAnswer: (JsonElement) -> Unit) {
    Grid(choices, columns = 2, modifier = Modifier.fillMaxWidth()) { c, m ->
        IconTile(c.label, contentIcon(c.icon), { if (enabled) onAnswer(c.value) }, m)
    }
}

/** Multiple choice: toggle icon cards, then "Done". "None / don't know" clears the others (and vice versa). */
@Composable
fun MultiAnswer(questionId: String, choices: List<Choice>, enabled: Boolean, onAnswer: (JsonElement) -> Unit) {
    val picked = remember(questionId) { mutableStateListOf<String>() }
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Grid(choices, columns = 2, modifier = Modifier.fillMaxWidth()) { c, m ->
            val k = c.key()
            IconTile(c.label, contentIcon(c.icon), {
                when {
                    k in picked -> picked.remove(k)
                    k in EXCLUSIVE -> { picked.clear(); picked.add(k) }
                    else -> { picked.removeAll { it in EXCLUSIVE }; picked.add(k) }
                }
            }, m, selected = k in picked)
        }
        BigButton(tr(R.string.answer_done), Icons.Filled.Check, {
            onAnswer(JsonArray(choices.filter { it.key() in picked }.map { it.value }))
        }, Modifier.fillMaxWidth(), enabled = enabled && picked.isNotEmpty())
    }
}
