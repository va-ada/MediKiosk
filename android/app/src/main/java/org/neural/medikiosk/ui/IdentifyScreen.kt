package org.neural.medikiosk.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.Badge
import androidx.compose.material.icons.filled.Man
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.PersonAdd
import androidx.compose.material.icons.filled.Woman
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.neural.medikiosk.IntakeViewModel
import org.neural.medikiosk.LocalActivityPing
import org.neural.medikiosk.R
import org.neural.medikiosk.data.errorCode
import org.neural.medikiosk.net.AbhaVerifyRequest
import org.neural.medikiosk.net.Patient
import org.neural.medikiosk.net.RegisterRequest
import org.neural.medikiosk.net.Sex

private enum class IdStep { CHOOSE, ABHA, OTP, NAME, AGE, SEX }

/**
 * Identify (journey step 1): ABHA number + OTP (mocked, §4.2) or register as a new patient.
 * Never blocks: a failed ABHA lookup offers the new-patient path.
 */
@Composable
fun IdentifyScreen(vm: IntakeViewModel, onIdentified: (Patient) -> Unit, onExit: () -> Unit) {
    var step by rememberSaveable { mutableStateOf(IdStep.CHOOSE) }
    val ping = LocalActivityPing.current
    var abha by rememberSaveable { mutableStateOf("") }
    var otp by rememberSaveable { mutableStateOf("") }
    var name by rememberSaveable { mutableStateOf("") }
    var age by rememberSaveable { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    val keyboard = LocalSoftwareKeyboardController.current
    fun go(to: IdStep) { keyboard?.hide(); error = null; step = to }
    val back: () -> Unit = {
        when (step) {
            IdStep.CHOOSE -> onExit()
            IdStep.ABHA, IdStep.NAME -> go(IdStep.CHOOSE)
            IdStep.OTP -> go(IdStep.ABHA)
            IdStep.AGE -> go(IdStep.NAME)
            IdStep.SEX -> go(IdStep.AGE)
        }
    }
    BackHandler(onBack = back)

    fun submit(call: suspend () -> Result<Patient>) {
        if (busy) return
        busy = true; error = null
        scope.launch {
            val r = call()
            busy = false
            r.onSuccess { vm.patient = it; onIdentified(it) }
            error = r.errorCode()
        }
    }

    KioskScaffold(audioKey = null) {
        ScreenBody {
            when (step) {
                IdStep.CHOOSE -> {
                    Heading(tr(R.string.identify_title))
                    BigButton(tr(R.string.id_have_abha), Icons.Filled.Badge, { go(IdStep.ABHA) }, Modifier.fillMaxWidth(), minHeight = 110.dp)
                    BigButton(tr(R.string.id_new_patient), Icons.Filled.PersonAdd, { go(IdStep.NAME) }, Modifier.fillMaxWidth(), minHeight = 110.dp)
                }
                IdStep.ABHA -> {
                    Heading(tr(R.string.id_enter_abha))
                    DigitDisplay((listOf(abha.take(2)) + abha.drop(2).chunked(4)).filter { it.isNotEmpty() }.joinToString("-"),
                        "__-____-____-____")
                    ErrorCard(error)
                    if (error == "abha_not_found") {
                        BigOutlinedButton(tr(R.string.id_new_patient), Icons.Filled.PersonAdd, { go(IdStep.NAME) }, Modifier.fillMaxWidth())
                    }
                    NumericKeypad({ if (abha.length < 14) abha += it }, { abha = abha.dropLast(1) })
                    NavRow(back, tr(R.string.next), enabled = abha.length == 14) { otp = ""; go(IdStep.OTP) }
                }
                IdStep.OTP -> {
                    Heading(tr(R.string.id_enter_otp))
                    Text(tr(R.string.id_otp_hint), style = MaterialTheme.typography.bodyMedium)
                    DigitDisplay(otp.toList().joinToString(" "), "_ _ _ _ _ _")
                    ErrorCard(error)
                    if (error == "abha_not_found" || error == "invalid_abha") {
                        BigOutlinedButton(tr(R.string.id_new_patient), Icons.Filled.PersonAdd, { go(IdStep.NAME) }, Modifier.fillMaxWidth())
                    }
                    NumericKeypad({ if (otp.length < 6) otp += it }, { otp = otp.dropLast(1) })
                    NavRow(back, tr(R.string.next), enabled = otp.length == 6 && !busy, busy = busy) {
                        submit { vm.repo.call { abhaVerify(AbhaVerifyRequest(abha, otp)) } }
                    }
                }
                IdStep.NAME -> {
                    Heading(tr(R.string.id_your_name))
                    Text(tr(R.string.id_name_hint), style = MaterialTheme.typography.bodyMedium)
                    OutlinedTextField(
                        value = name,
                        onValueChange = { ping(); if (it.length <= 120) name = it },
                        textStyle = MaterialTheme.typography.headlineMedium,
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words, imeAction = ImeAction.Next),
                        keyboardActions = KeyboardActions(onNext = { if (name.isNotBlank()) go(IdStep.AGE) }),
                        modifier = Modifier.fillMaxWidth(),
                    )
                    NavRow(back, tr(R.string.next), enabled = name.isNotBlank()) { go(IdStep.AGE) }
                }
                IdStep.AGE -> {
                    Heading(tr(R.string.id_your_age))
                    DigitDisplay(age, tr(R.string.id_age_years))
                    val ageOk = age.toIntOrNull()?.let { it in 0..120 } == true
                    if (age.isNotEmpty() && !ageOk) ErrorCard("validation_error")
                    NumericKeypad({ if (age.length < 3) age = (age + it).trimStart('0').ifEmpty { "0" } }, { age = age.dropLast(1) })
                    NavRow(back, tr(R.string.next), enabled = ageOk) { go(IdStep.SEX) }
                }
                IdStep.SEX -> {
                    Heading(tr(R.string.id_your_sex))
                    ErrorCard(error)
                    val options = listOf(
                        Triple(Sex.F, R.string.sex_female, Icons.Filled.Woman),
                        Triple(Sex.M, R.string.sex_male, Icons.Filled.Man),
                        Triple(Sex.O, R.string.sex_other, Icons.Filled.Person),
                    )
                    val lang = LocalLang.current
                    options.forEach { (code, label, icon) ->
                        BigButton(tr(label), icon, {
                            submit { vm.repo.call { register(RegisterRequest(name.trim(), age.toInt(), code, lang)) } }
                        }, Modifier.fillMaxWidth(), enabled = !busy, minHeight = 96.dp)
                    }
                    if (busy) CircularProgressIndicator()
                    BigOutlinedButton(tr(R.string.back), Icons.AutoMirrored.Filled.ArrowBack, back, Modifier.fillMaxWidth())
                }
            }
        }
    }
}

/** Back + primary "Next" row used by step-by-step screens. */
@Composable
fun NavRow(onBack: () -> Unit, nextLabel: String, enabled: Boolean, busy: Boolean = false, onNext: () -> Unit) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        BigOutlinedButton(tr(R.string.back), Icons.AutoMirrored.Filled.ArrowBack, onBack, Modifier.weight(1f))
        if (busy) {
            Row(Modifier.weight(1f), horizontalArrangement = Arrangement.Center) { CircularProgressIndicator() }
        } else {
            BigButton(nextLabel, Icons.AutoMirrored.Filled.ArrowForward, onNext, Modifier.weight(1f), enabled = enabled)
        }
    }
}
