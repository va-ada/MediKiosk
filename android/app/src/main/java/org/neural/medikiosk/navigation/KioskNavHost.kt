package org.neural.medikiosk.navigation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import kotlinx.coroutines.launch
import org.neural.medikiosk.IntakeViewModel
import org.neural.medikiosk.LocalWipe
import org.neural.medikiosk.R
import org.neural.medikiosk.data.DeviceSettings
import org.neural.medikiosk.ui.BigButton
import org.neural.medikiosk.ui.DeviceSettingsScreen
import org.neural.medikiosk.ui.DoneScreen
import org.neural.medikiosk.ui.EmergencyScreen
import org.neural.medikiosk.ui.ResumeScanner
import org.neural.medikiosk.ui.ConsentScreen
import org.neural.medikiosk.ui.HistoryScreen
import org.neural.medikiosk.ui.IdentifyScreen
import org.neural.medikiosk.ui.InformantScreen
import org.neural.medikiosk.ui.KioskScaffold
import org.neural.medikiosk.ui.LocalLang
import org.neural.medikiosk.ui.NeedHelpScreen
import org.neural.medikiosk.ui.StartScreen
import org.neural.medikiosk.ui.TokenScreen
import org.neural.medikiosk.ui.TriageScreen
import org.neural.medikiosk.ui.tr

/** The kiosk navigation graph. The patient's language (from [IntakeViewModel]) is provided to every screen. */
@Composable
fun KioskNavHost(vm: IntakeViewModel, settings: DeviceSettings) {
    val nav = rememberNavController()
    val scope = rememberCoroutineScope()
    val startRoute = Routes.START

    val wipe: () -> Unit = { vm.clear(); nav.toStart(startRoute) }

    CompositionLocalProvider(LocalNavController provides nav, LocalLang provides vm.language, LocalWipe provides wipe) {
        NavHost(navController = nav, startDestination = startRoute) {
            composable(Routes.START) {
                StartScreen(
                    onLanguage = { lang -> vm.clear(); vm.language = lang; nav.forward(Routes.IDENTIFY) },
                    onOpenSettings = { nav.forward(Routes.DEVICE_SETTINGS) },
                    onResume = { nav.forward(Routes.RESUME) },
                )
            }
            composable(Routes.DEVICE_SETTINGS) {
                DeviceSettingsScreen(
                    settings,
                    onSave = { scope.launch { vm.settingsRepo.save(it); nav.toStart(startRoute) } },
                    onClose = { nav.popBackStack() },
                )
            }
            composable(Routes.HELP) { NeedHelpScreen(onBack = { nav.popBackStack() }) }
            composable(Routes.EMERGENCY) { EmergencyScreen(vm, settings, onBack = { nav.popBackStack() }) }
            composable(Routes.IDENTIFY) {
                IdentifyScreen(vm, onIdentified = { nav.forward(Routes.INFORMANT) }, onExit = { vm.clear(); nav.toStart(startRoute) })
            }
            composable(Routes.INFORMANT) {
                InformantScreen(vm, onDone = { nav.forward(Routes.CONSENT) }, onBack = { nav.popBackStack() })
            }
            composable(Routes.CONSENT) {
                ConsentScreen(vm, onDone = { nav.forward(Routes.TRIAGE) }, onBack = { nav.popBackStack() })
            }
            composable(Routes.TRIAGE) {
                TriageScreen(vm, onDone = { nav.forward(Routes.TOKEN) }, onBack = { nav.popBackStack() })
            }
            composable(Routes.TOKEN) {
                TokenScreen(vm, onContinueHere = { nav.forward(Routes.HISTORY) }, onFinishHere = { nav.forward(Routes.DONE) })
            }
            composable(Routes.HISTORY) { HistoryScreen(vm, onDone = { nav.forward(Routes.DOCUMENTS) }) }
            composable(Routes.DOCUMENTS) { Placeholder(R.string.docs_title) }
            composable(Routes.READBACK) { Placeholder(R.string.done) }
            composable(Routes.DONE) { DoneScreen(vm) }
            composable(Routes.RESUME) {
                ResumeScanner(vm, onResumed = { nav.forward(resumeRoute(it.status)) }, onBack = { nav.popBackStack() })
            }
        }
    }
}

/** Where a scanned token slip continues, by session status (§2 session_status). */
fun resumeRoute(status: String): String = when (status) {
    "identifying" -> Routes.CONSENT
    "consented" -> Routes.TRIAGE
    "triaged", "history" -> Routes.HISTORY
    "documents" -> Routes.DOCUMENTS
    "verifying" -> Routes.READBACK
    else -> Routes.DONE  // submitted / with_doctor / closed: nothing left to answer
}

/** Stand-in for screens later cards build. */
@Composable
private fun Placeholder(titleRes: Int) {
    val nav = LocalNavController.current
    KioskScaffold(audioKey = null) {
        Column(
            Modifier.fillMaxSize().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(24.dp, Alignment.CenterVertically),
        ) {
            Text(tr(titleRes), style = MaterialTheme.typography.headlineLarge, textAlign = TextAlign.Center)
            BigButton(tr(R.string.back), Icons.AutoMirrored.Filled.ArrowBack, { nav.popBackStack() }, Modifier.fillMaxWidth())
        }
    }
}
