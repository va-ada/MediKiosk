package org.neural.medikiosk.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import org.neural.medikiosk.IntakeViewModel
import org.neural.medikiosk.R
import org.neural.medikiosk.data.errorCode
import org.neural.medikiosk.net.AnswerRequest
import org.neural.medikiosk.net.NextQuestion
import org.neural.medikiosk.net.Question
import org.neural.medikiosk.net.QuestionType
import org.neural.medikiosk.ui.answers.ChoiceAnswer
import org.neural.medikiosk.ui.answers.DurationAnswer
import org.neural.medikiosk.ui.answers.FreeAnswer
import org.neural.medikiosk.ui.answers.MultiAnswer
import org.neural.medikiosk.ui.answers.NumberAnswer
import org.neural.medikiosk.ui.answers.ScaleAnswer

/**
 * History loop (journey step 4): `GET next-question` → render by type → `POST answers` → render `next`,
 * until `done: true`. Questions come only from the server's graph (rule 2). Back re-opens the previous
 * question (a new answer replaces the old one on the server).
 */
@Composable
fun HistoryScreen(vm: IntakeViewModel, onDone: () -> Unit) {
    val session = vm.session ?: return
    val lang = LocalLang.current
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    fun show(next: NextQuestion) {
        if (next.done || next.question == null) {
            vm.question = null
            vm.previousQuestions.clear()
            onDone()
        } else {
            vm.question = next.question
        }
    }

    fun load() {
        busy = true; error = null
        scope.launch {
            val r = vm.repo.call { nextQuestion(session.id, lang) }
            busy = false
            r.onSuccess(::show)
            error = r.errorCode()
        }
    }

    fun answer(q: Question, value: JsonElement) {
        if (busy) return
        busy = true; error = null
        scope.launch {
            val r = vm.repo.call { answer(session.id, AnswerRequest(q.id, "tap", value), lang) }
            busy = false
            r.onSuccess {
                if (it.alerts.isNotEmpty()) vm.triageAlerts = vm.triageAlerts + it.alerts
                vm.previousQuestions.add(q)
                show(it.next)
            }
            error = r.errorCode()
        }
    }

    // Fresh start or resume: ask the server for the first unanswered question.
    LaunchedEffect(session.id) { if (vm.question == null) load() }
    BackHandler(enabled = vm.previousQuestions.isNotEmpty()) {
        vm.question = vm.previousQuestions.removeAt(vm.previousQuestions.lastIndex)
        error = null
    }

    val q = vm.question
    KioskScaffold(audioKey = q?.audio) {
        ScreenBody {
            if (vm.triageAlerts.isNotEmpty()) NurseInformedBanner()
            ErrorCard(error)
            if (q == null) {
                if (busy) CircularProgressIndicator()
                if (error != null) BigButton(tr(R.string.try_again), Icons.AutoMirrored.Filled.ArrowForward, ::load, Modifier.fillMaxWidth())
                return@ScreenBody
            }
            q.progress?.let { p ->
                val total = (p.answered + p.remainingEstimate).coerceAtLeast(1)
                LinearProgressIndicator(progress = { p.answered.toFloat() / total }, modifier = Modifier.fillMaxWidth())
                Text(tr(R.string.history_progress, p.answered, total), style = MaterialTheme.typography.bodyMedium)
            }
            Heading(q.text)
            if (busy) CircularProgressIndicator()
            AnswerInput(q, enabled = !busy) { answer(q, it) }
            if (vm.previousQuestions.isNotEmpty()) {
                BigOutlinedButton(tr(R.string.history_previous), Icons.AutoMirrored.Filled.ArrowBack, {
                    vm.question = vm.previousQuestions.removeAt(vm.previousQuestions.lastIndex); error = null
                }, Modifier.fillMaxWidth(), enabled = !busy)
            }
        }
    }
}

/** The tap input for a question, by `type` (§2 question_type). */
@Composable
fun AnswerInput(q: Question, enabled: Boolean, onAnswer: (JsonElement) -> Unit) {
    when (q.type) {
        QuestionType.CHOICE -> ChoiceAnswer(q.choices, enabled, onAnswer)
        QuestionType.MULTI -> MultiAnswer(q.id, q.choices, enabled, onAnswer)
        QuestionType.YESNO -> YesNoButtons(selected = null) { onAnswer(kotlinx.serialization.json.JsonPrimitive(it)) }
        QuestionType.NUMBER -> NumberAnswer(q.id, q.choices, enabled, onAnswer)
        QuestionType.DURATION -> DurationAnswer(q.id, q.choices, enabled, onAnswer)
        QuestionType.SCALE -> ScaleAnswer(enabled, onAnswer)
        else -> FreeAnswer(q.id, q.choices, enabled, onAnswer)
    }
}
