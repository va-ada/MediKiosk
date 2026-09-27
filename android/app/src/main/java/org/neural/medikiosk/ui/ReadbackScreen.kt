package org.neural.medikiosk.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.automirrored.filled.HelpOutline
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.neural.medikiosk.IntakeViewModel
import org.neural.medikiosk.R
import org.neural.medikiosk.data.errorCode
import org.neural.medikiosk.net.ReadbackItem
import org.neural.medikiosk.net.ReadbackRequest
import org.neural.medikiosk.net.ReadbackResponse
import org.neural.medikiosk.ui.theme.Green

/**
 * Read-back (journey step 6): `sys_readback_intro`, then each item as big text, spoken with TextToSpeech
 * (text only if no voice); Yes / No / Not sure → `POST readback`; after the last → `POST submit` → Done.
 */
@Composable
fun ReadbackScreen(vm: IntakeViewModel, onDone: () -> Unit) {
    val session = vm.session ?: return
    val lang = LocalLang.current
    val scope = rememberCoroutineScope()
    var items by remember { mutableStateOf<List<ReadbackItem>?>(null) }
    var index by rememberSaveable { mutableIntStateOf(-1) }  // -1 = intro
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    BackHandler(enabled = index > 0) { index -= 1 }

    fun load() {
        busy = true; error = null
        scope.launch {
            val r = vm.repo.call { readback(session.id, lang) }
            busy = false
            r.onSuccess { items = it.items }
            error = r.errorCode()
        }
    }

    fun submit() {
        busy = true; error = null
        scope.launch {
            val r = vm.repo.call { submit(session.id) }
            busy = false
            r.onSuccess { vm.session = it.session; onDone() }
            error = r.errorCode()
        }
    }

    fun respond(item: ReadbackItem, response: String) {
        busy = true; error = null
        scope.launch {
            val r = vm.repo.call { readbackAnswer(session.id, ReadbackRequest(item.factId, response)) }
            busy = false
            if (r.isSuccess) {
                if (index >= (items?.lastIndex ?: 0)) submit() else index += 1
            }
            error = r.errorCode()
        }
    }

    LaunchedEffect(session.id) { if (items == null) load() }
    val list = items
    val item = list?.getOrNull(index)

    KioskScaffold(audioKey = if (index < 0) "sys_readback_intro" else null, speech = item?.text) {
        ScreenBody {
            ErrorCard(error)
            when {
                list == null -> {
                    if (busy) CircularProgressIndicator()
                    if (error != null) BigButton(tr(R.string.try_again), Icons.AutoMirrored.Filled.ArrowForward, ::load, Modifier.fillMaxWidth())
                }
                index < 0 -> {
                    Heading(tr(R.string.rb_title))
                    Text(tr(R.string.rb_intro), style = MaterialTheme.typography.bodyLarge, textAlign = TextAlign.Center)
                    if (busy) CircularProgressIndicator()
                    if (list.isEmpty()) {
                        BigButton(tr(R.string.rb_send), Icons.Filled.Send, ::submit, Modifier.fillMaxWidth(), enabled = !busy, minHeight = 96.dp)
                    } else {
                        BigButton(tr(R.string.rb_start), Icons.AutoMirrored.Filled.ArrowForward, { index = 0 }, Modifier.fillMaxWidth(), minHeight = 96.dp)
                    }
                }
                item != null -> {
                    LinearProgressIndicator(progress = { (index + 1f) / list.size }, modifier = Modifier.fillMaxWidth())
                    Text(tr(R.string.rb_n_of_m, index + 1, list.size), style = MaterialTheme.typography.bodyMedium)
                    Heading(tr(R.string.rb_is_this_right))
                    Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp), border = BorderStroke(3.dp, MaterialTheme.colorScheme.primary),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                        Text(item.text, style = MaterialTheme.typography.headlineMedium, textAlign = TextAlign.Center,
                            modifier = Modifier.fillMaxWidth().padding(20.dp))
                    }
                    if (busy) CircularProgressIndicator()
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        BigButton(tr(R.string.rb_yes), Icons.Filled.Check, { respond(item, ReadbackResponse.YES) }, Modifier.fillMaxWidth(),
                            container = Green, content = Color.White, enabled = !busy, minHeight = 96.dp)
                        BigButton(tr(R.string.rb_no), Icons.Filled.Close, { respond(item, ReadbackResponse.NO) }, Modifier.fillMaxWidth(),
                            enabled = !busy, minHeight = 96.dp)
                        BigOutlinedButton(tr(R.string.rb_not_sure), Icons.AutoMirrored.Filled.HelpOutline, { respond(item, ReadbackResponse.NOT_SURE) },
                            Modifier.fillMaxWidth(), enabled = !busy)
                    }
                }
                else -> {  // all answered (e.g. a failed submit): offer to send again
                    if (busy) CircularProgressIndicator()
                    BigButton(tr(R.string.rb_send), Icons.Filled.Send, ::submit, Modifier.fillMaxWidth(), enabled = !busy)
                }
            }
        }
    }
}
