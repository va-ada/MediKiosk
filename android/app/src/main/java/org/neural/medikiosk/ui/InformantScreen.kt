package org.neural.medikiosk.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Boy
import androidx.compose.material.icons.filled.Elderly
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Girl
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.SupervisorAccount
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.neural.medikiosk.IntakeViewModel
import org.neural.medikiosk.R
import org.neural.medikiosk.data.errorCode
import org.neural.medikiosk.net.InformantType
import org.neural.medikiosk.net.SessionCreateRequest

/** Who is answering (journey step 2a): the patient, or someone else for them → `POST /api/sessions`. */
@Composable
fun InformantScreen(vm: IntakeViewModel, onDone: () -> Unit, onBack: () -> Unit) {
    val patient = vm.patient ?: return
    var proxy by rememberSaveable { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    BackHandler { if (proxy) proxy = false else onBack() }

    fun create(informant: String, relation: String?) {
        // One session per patient visit: coming back here keeps the session already created.
        if (vm.session?.patientId == patient.id) return onDone()
        busy = true; error = null
        scope.launch {
            val r = vm.repo.call { createSession(SessionCreateRequest(patient.id, informant, relation)) }
            busy = false
            r.onSuccess { vm.session = it; onDone() }
            error = r.errorCode()
        }
    }

    KioskScaffold(audioKey = null, speech = tr(if (proxy) R.string.inf_relation else R.string.inf_who_answers)) {
        ScreenBody {
            Text(tr(R.string.hello_name, patient.name), style = MaterialTheme.typography.titleLarge)
            ErrorCard(error)
            if (busy) CircularProgressIndicator()
            if (!proxy) {
                Heading(tr(R.string.inf_who_answers))
                BigButton(tr(R.string.inf_myself), Icons.Filled.Person, { create(InformantType.SELF, null) },
                    Modifier.fillMaxWidth(), enabled = !busy, minHeight = 110.dp)
                BigButton(tr(R.string.inf_someone_else), Icons.Filled.SupervisorAccount, { proxy = true },
                    Modifier.fillMaxWidth(), enabled = !busy, minHeight = 110.dp)
                BigOutlinedButton(tr(R.string.back), Icons.AutoMirrored.Filled.ArrowBack, onBack, Modifier.fillMaxWidth())
            } else {
                Heading(tr(R.string.inf_relation))
                val relations = listOf(
                    Triple("son", R.string.rel_son, Icons.Filled.Boy),
                    Triple("daughter", R.string.rel_daughter, Icons.Filled.Girl),
                    Triple("spouse", R.string.rel_spouse, Icons.Filled.Favorite),
                    Triple("parent", R.string.rel_parent, Icons.Filled.Elderly),
                    Triple("other", R.string.rel_other, Icons.Filled.People),
                )
                Grid(relations, columns = 2) { (code, label, icon), m ->
                    IconTile(tr(label), icon, { if (!busy) create(InformantType.PROXY, code) }, m)
                }
                BigOutlinedButton(tr(R.string.back), Icons.AutoMirrored.Filled.ArrowBack, { proxy = false }, Modifier.fillMaxWidth())
            }
        }
    }
}
