package org.neural.medikiosk.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.rememberCoroutineScope
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import kotlinx.coroutines.launch
import org.neural.medikiosk.IntakeViewModel
import org.neural.medikiosk.LocalInactivityEnabled
import org.neural.medikiosk.LocalWipe
import org.neural.medikiosk.net.DeviceMode
import org.neural.medikiosk.ui.patientapp.LiveStatusCard
import org.neural.medikiosk.ui.patientapp.LocalTwoPane
import org.neural.medikiosk.ui.patientapp.PatientAppFrame
import org.neural.medikiosk.ui.patientapp.PatientHomeScreen
import org.neural.medikiosk.data.DeviceSettings
import org.neural.medikiosk.ui.DeviceSettingsScreen
import org.neural.medikiosk.ui.DocumentsScreen
import org.neural.medikiosk.ui.DoneScreen
import org.neural.medikiosk.ui.HallStartScreen
import org.neural.medikiosk.ui.SettingsScreen
import org.neural.medikiosk.ui.EmergencyScreen
import org.neural.medikiosk.ui.ReadbackScreen
import org.neural.medikiosk.ui.ResumeScanner
import org.neural.medikiosk.ui.ConsentScreen
import org.neural.medikiosk.ui.HistoryScreen
import org.neural.medikiosk.ui.IdentifyScreen
import org.neural.medikiosk.ui.InformantScreen
import org.neural.medikiosk.ui.LocalLang
import org.neural.medikiosk.ui.NeedHelpScreen
import org.neural.medikiosk.ui.StartScreen
import org.neural.medikiosk.ui.TokenScreen
import org.neural.medikiosk.ui.TriageScreen

/** The kiosk navigation graph. The patient's language (from [IntakeViewModel]) is provided to every screen. */
@Composable
fun KioskNavHost(vm: IntakeViewModel, settings: DeviceSettings) {
    val nav = rememberNavController()
    val scope = rememberCoroutineScope()
    val patientApp = settings.deviceMode == DeviceMode.PATIENT_APP
    val hall = settings.deviceMode == DeviceMode.HALL
    val startRoute = when {
        patientApp -> Routes.PATIENT_HOME
        hall -> Routes.HALL_START
        else -> Routes.START
    }
    // Patient app: the live status card sits in the left pane when unfolded, else inside the token/done screens.
    val statusCard: (@Composable () -> Unit)? = if (patientApp) ({ if (!LocalTwoPane.current) LiveStatusCard(vm) }) else null

    val wipe: () -> Unit = { vm.clear(); nav.toStart(startRoute) }

    CompositionLocalProvider(
        LocalNavController provides nav, LocalLang provides vm.language, LocalWipe provides wipe,
        LocalInactivityEnabled provides !patientApp,
    ) { PatientAppFrameIf(patientApp, vm) {
        NavHost(navController = nav, startDestination = startRoute) {
            composable(Routes.PATIENT_HOME) {
                PatientHomeScreen(
                    onLanguage = { vm.language = it },
                    onCheckIn = { val lang = vm.language; vm.clear(); vm.language = lang; nav.forward(Routes.IDENTIFY) },
                    onOpenSettings = { nav.forward(Routes.DEVICE_SETTINGS) },
                )
            }
            composable(Routes.START) {
                StartScreen(
                    onLanguage = { lang -> vm.clear(); vm.language = lang; nav.forward(Routes.IDENTIFY) },
                    onOpenSettings = { nav.forward(Routes.DEVICE_SETTINGS) },
                    onResume = { nav.forward(Routes.RESUME) },
                )
            }
            composable(Routes.HALL_START) {
                HallStartScreen(onScan = { vm.clear(); nav.forward(Routes.RESUME) }, onOpenSettings = { nav.forward(Routes.DEVICE_SETTINGS) })
            }
            composable(Routes.DEVICE_SETTINGS) {
                DeviceSettingsScreen(
                    settings,
                    // keep the accessibility toggles as saved (live) by SettingsScreen
                    onSave = { draft ->
                        val now = vm.settings.value ?: settings
                        scope.launch {
                            vm.settingsRepo.save(draft.copy(largeText = now.largeText, highContrast = now.highContrast,
                                slowPrompts = now.slowPrompts, handsetMode = now.handsetMode))
                            nav.toStart(startRoute)
                        }
                    },
                    onClose = { nav.popBackStack() },
                    onAccessibility = { nav.forward(Routes.ACCESSIBILITY) },
                )
            }
            composable(Routes.ACCESSIBILITY) {
                SettingsScreen(settings, onChange = { scope.launch { vm.settingsRepo.save(it) } }, onClose = { nav.popBackStack() })
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
                TokenScreen(vm, onContinueHere = { nav.forward(Routes.HISTORY) }, onFinishHere = { nav.forward(Routes.DONE) },
                    statusCard = statusCard, showHallOption = !patientApp)
            }
            composable(Routes.HISTORY) { HistoryScreen(vm, onDone = { nav.forward(if (hall) Routes.READBACK else Routes.DOCUMENTS) }) }
            composable(Routes.DOCUMENTS) { DocumentsScreen(vm, onDone = { nav.forward(Routes.READBACK) }) }
            composable(Routes.READBACK) { ReadbackScreen(vm, onDone = { nav.forward(Routes.DONE) }) }
            composable(Routes.DONE) { DoneScreen(vm, autoWipe = !patientApp, statusCard = statusCard) }
            composable(Routes.RESUME) {
                ResumeScanner(vm, onResumed = { nav.forward(resumeRoute(it.status, hall)) }, onBack = { nav.popBackStack() })
            }
        }
    } }
}

/** Wrap in the patient-app two-pane frame only in PATIENT_APP mode. */
@Composable
private fun PatientAppFrameIf(patientApp: Boolean, vm: IntakeViewModel, content: @Composable () -> Unit) =
    if (patientApp) PatientAppFrame(vm, content) else content()

/** Where a scanned token slip continues, by session status (§2 session_status). */
fun resumeRoute(status: String, hall: Boolean = false): String = when (status) {
    "identifying" -> if (hall) Routes.DONE else Routes.CONSENT  // the hall station only continues triaged visits
    "consented" -> if (hall) Routes.DONE else Routes.TRIAGE
    "triaged", "history" -> Routes.HISTORY
    "documents" -> if (hall) Routes.READBACK else Routes.DOCUMENTS  // no documents at the hall station
    "verifying" -> Routes.READBACK
    else -> Routes.DONE  // submitted / with_doctor / closed: nothing left to answer
}
