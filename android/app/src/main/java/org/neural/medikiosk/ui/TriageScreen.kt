package org.neural.medikiosk.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.automirrored.filled.HelpOutline
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.neural.medikiosk.IntakeViewModel
import org.neural.medikiosk.R
import org.neural.medikiosk.data.errorCode
import org.neural.medikiosk.net.RedFlags
import org.neural.medikiosk.net.TriageRequest
import org.neural.medikiosk.ui.theme.Green

/** Mirrors content/triage.yaml `complaints` (§9.2): code, icon, labels. */
data class Complaint(val code: String, val icon: String, val en: String, val hi: String)

val COMPLAINTS = listOf(
    Complaint("joint_pain", "joint", "Joint pain", "जोड़ों का दर्द"),
    Complaint("fever", "fever", "Fever", "बुखार"),
    Complaint("cough", "cough", "Cough or cold", "खाँसी या ज़ुकाम"),
    Complaint("stomach", "stomach", "Stomach problem", "पेट की तकलीफ़"),
    Complaint("headache", "headache", "Headache", "सिर दर्द"),
    Complaint("chest_pain", "chest", "Chest pain", "सीने में दर्द"),
    Complaint("breathing", "breathing", "Breathing problem", "साँस की तकलीफ़"),
    Complaint("skin", "skin", "Skin problem", "त्वचा की तकलीफ़"),
    Complaint("other", "other", "Something else", "कुछ और"),
)

/** Mirrors content/triage.yaml `redflag_questions` — always asked, in this order; audio key = slot. */
data class RedFlagQuestion(val slot: String, val en: String, val hi: String)

val REDFLAG_QUESTIONS = listOf(
    RedFlagQuestion("chest_pain", "Do you have chest pain now?", "क्या अभी सीने में दर्द है?"),
    RedFlagQuestion("breathless", "Are you finding it hard to breathe?", "क्या साँस लेने में तकलीफ़ है?"),
    RedFlagQuestion("stroke_signs", "Sudden weakness, face drooping or slurred speech?", "क्या अचानक कमज़ोरी, चेहरा टेढ़ा या बोलने में दिक्कत है?"),
    RedFlagQuestion("heavy_bleeding", "Are you bleeding heavily?", "क्या बहुत ज़्यादा खून बह रहा है?"),
    RedFlagQuestion("fainted", "Did you faint today?", "क्या आज आप बेहोश हुए?"),
)

private const val STEP_COMPLAINT = 0
private const val STEP_BODY = 1
private const val STEP_FIRST_FLAG = 2

/**
 * Triage (journey step 3): main complaint (icons), body map for joint pain, the 5 red-flag yes/no questions
 * → `POST /api/sessions/{id}/triage` → token.
 */
@Composable
fun TriageScreen(vm: IntakeViewModel, onDone: () -> Unit, onBack: () -> Unit) {
    val session = vm.session ?: return
    val lang = LocalLang.current
    var step by rememberSaveable { mutableIntStateOf(STEP_COMPLAINT) }
    var complaint by rememberSaveable { mutableStateOf<String?>(null) }
    var bodyPart by rememberSaveable { mutableStateOf<String?>(null) }
    val flags = remember { mutableStateMapOf<String, Boolean>() }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    fun previous() {
        error = null
        step = when {
            step == STEP_COMPLAINT -> return onBack()
            step == STEP_FIRST_FLAG && complaint != "joint_pain" -> STEP_COMPLAINT
            else -> step - 1
        }
    }
    BackHandler(onBack = ::previous)

    fun submit() {
        val c = complaint ?: return
        busy = true; error = null
        val rf = RedFlags(flags["chest_pain"] == true, flags["breathless"] == true, flags["stroke_signs"] == true,
            flags["heavy_bleeding"] == true, flags["fainted"] == true)
        val text = COMPLAINTS.first { it.code == c }.let { pick(lang, it.hi, it.en) }
        scope.launch {
            val r = vm.repo.call { triage(session.id, TriageRequest(c, text, if (c == "joint_pain") bodyPart else null, rf)) }
            busy = false
            r.onSuccess { vm.session = it.session; vm.token = it.token; vm.triageAlerts = it.alerts; onDone() }
            error = r.errorCode()
        }
    }

    val flagIndex = step - STEP_FIRST_FLAG
    val audioKey = if (flagIndex in REDFLAG_QUESTIONS.indices) REDFLAG_QUESTIONS[flagIndex].slot else null

    val speech = when (step) {
        STEP_COMPLAINT -> tr(R.string.triage_what_problem)
        STEP_BODY -> tr(R.string.triage_where_pain)
        else -> null
    }
    KioskScaffold(audioKey = audioKey, speech = speech) {
        ScreenBody {
            when {
                step == STEP_COMPLAINT -> {
                    Heading(tr(R.string.triage_what_problem))
                    Grid(COMPLAINTS, columns = 2) { c, m ->
                        IconTile(pick(lang, c.hi, c.en), contentIcon(c.icon), {
                            complaint = c.code
                            step = if (c.code == "joint_pain") STEP_BODY else STEP_FIRST_FLAG
                        }, m, selected = complaint == c.code)
                    }
                    BigOutlinedButton(tr(R.string.back), Icons.AutoMirrored.Filled.ArrowBack, ::previous, Modifier.fillMaxWidth())
                }
                step == STEP_BODY -> {
                    Heading(tr(R.string.triage_where_pain))
                    BodyMap(bodyPart, { bodyPart = it }, Modifier.fillMaxWidth())
                    BigOutlinedButton(tr(R.string.triage_somewhere_else), Icons.AutoMirrored.Filled.HelpOutline,
                        { bodyPart = null; step = STEP_FIRST_FLAG }, Modifier.fillMaxWidth())
                    NavRow(::previous, tr(R.string.next), enabled = bodyPart != null) { step = STEP_FIRST_FLAG }
                }
                else -> {
                    val q = REDFLAG_QUESTIONS[flagIndex]
                    LinearProgressIndicator(progress = { (flagIndex + 1f) / REDFLAG_QUESTIONS.size }, modifier = Modifier.fillMaxWidth())
                    Text(tr(R.string.question_n_of_m, flagIndex + 1, REDFLAG_QUESTIONS.size), style = MaterialTheme.typography.bodyMedium)
                    Heading(pick(lang, q.hi, q.en))
                    ErrorCard(error)
                    if (busy) {
                        CircularProgressIndicator()
                    } else if (error != null) {
                        BigButton(tr(R.string.try_again), Icons.AutoMirrored.Filled.ArrowForward, ::submit, Modifier.fillMaxWidth())
                    } else {
                        YesNoButtons(selected = flags[q.slot]) { yes ->
                            flags[q.slot] = yes
                            if (flagIndex == REDFLAG_QUESTIONS.lastIndex) submit() else step += 1
                        }
                    }
                    BigOutlinedButton(tr(R.string.back), Icons.AutoMirrored.Filled.ArrowBack, ::previous, Modifier.fillMaxWidth(), enabled = !busy)
                }
            }
        }
    }
}

/** Big ✓ Yes / ✗ No pair (≥ 120 dp tall). */
@Composable
fun YesNoButtons(selected: Boolean?, onAnswer: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        BigButton(tr(R.string.yes), Icons.Filled.Check, { onAnswer(true) }, Modifier.weight(1f), minHeight = 140.dp,
            container = if (selected == true) MaterialTheme.colorScheme.secondary else Green, content = Color.White)
        BigButton(tr(R.string.no), Icons.Filled.Close, { onAnswer(false) }, Modifier.weight(1f), minHeight = 140.dp,
            container = if (selected == false) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.primary)
    }
}
