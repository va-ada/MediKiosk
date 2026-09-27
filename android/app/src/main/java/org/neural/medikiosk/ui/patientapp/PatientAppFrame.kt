package org.neural.medikiosk.ui.patientapp

import androidx.activity.compose.LocalActivity
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.VerticalDivider
import androidx.compose.material3.windowsizeclass.ExperimentalMaterial3WindowSizeClassApi
import androidx.compose.material3.windowsizeclass.WindowWidthSizeClass
import androidx.compose.material3.windowsizeclass.calculateWindowSizeClass
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.neural.medikiosk.IntakeViewModel

/** True when the patient app shows the live status in its own left pane (unfolded Z Fold / tablet). */
val LocalTwoPane = staticCompositionLocalOf { false }

/**
 * Patient-app layout: once a token exists, a wide window (Medium/Expanded width class, e.g. the unfolded
 * Z Fold) shows the live status card on the left and the current screen (question) on the right.
 */
@OptIn(ExperimentalMaterial3WindowSizeClassApi::class)
@Composable
fun PatientAppFrame(vm: IntakeViewModel, content: @Composable () -> Unit) {
    val activity = LocalActivity.current ?: return content()
    val wide = calculateWindowSizeClass(activity).widthSizeClass != WindowWidthSizeClass.Compact
    val twoPane = wide && vm.token != null
    CompositionLocalProvider(LocalTwoPane provides twoPane) {
        if (!twoPane) {
            content()
        } else {
            Row(Modifier.fillMaxSize()) {
                Box(Modifier.weight(0.4f).fillMaxHeight().verticalScroll(rememberScrollState()).padding(16.dp)) {
                    LiveStatusCard(vm)
                }
                VerticalDivider()
                Box(Modifier.weight(0.6f).fillMaxHeight()) { content() }
            }
        }
    }
}
