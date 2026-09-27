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
import org.neural.medikiosk.R
import org.neural.medikiosk.data.DeviceSettings
import org.neural.medikiosk.ui.BigButton
import org.neural.medikiosk.ui.DeviceSettingsScreen
import org.neural.medikiosk.ui.IdentifyScreen
import org.neural.medikiosk.ui.KioskScaffold
import org.neural.medikiosk.ui.LocalLang
import org.neural.medikiosk.ui.NeedHelpScreen
import org.neural.medikiosk.ui.StartScreen
import org.neural.medikiosk.ui.tr

/** The kiosk navigation graph. The patient's language (from [IntakeViewModel]) is provided to every screen. */
@Composable
fun KioskNavHost(vm: IntakeViewModel, settings: DeviceSettings) {
    val nav = rememberNavController()
    val scope = rememberCoroutineScope()
    val startRoute = Routes.START

    CompositionLocalProvider(LocalNavController provides nav, LocalLang provides vm.language) {
        NavHost(navController = nav, startDestination = startRoute) {
            composable(Routes.START) {
                StartScreen(
                    onLanguage = { lang -> vm.clear(); vm.language = lang; nav.forward(Routes.IDENTIFY) },
                    onOpenSettings = { nav.forward(Routes.DEVICE_SETTINGS) },
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
            composable(Routes.EMERGENCY) { Placeholder(R.string.emergency) }
            composable(Routes.IDENTIFY) {
                IdentifyScreen(vm, onIdentified = { nav.forward(Routes.INFORMANT) }, onExit = { vm.clear(); nav.toStart(startRoute) })
            }
            composable(Routes.INFORMANT) { Placeholder(R.string.identify_title) }
        }
    }
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
