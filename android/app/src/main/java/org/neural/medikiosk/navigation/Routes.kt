package org.neural.medikiosk.navigation

import androidx.compose.runtime.staticCompositionLocalOf
import androidx.navigation.NavHostController

/** Navigation routes of the single-activity app. */
object Routes {
    const val START = "start"
    const val DEVICE_SETTINGS = "device_settings"
    const val IDENTIFY = "identify"
    const val INFORMANT = "informant"
    const val CONSENT = "consent"
    const val TRIAGE = "triage"
    const val TOKEN = "token"
    const val HISTORY = "history"
    const val DOCUMENTS = "documents"
    const val READBACK = "readback"
    const val DONE = "done"
    const val EMERGENCY = "emergency"
    const val HELP = "help"
    const val RESUME = "resume"
    const val PATIENT_HOME = "patient_home"
    const val HALL_START = "hall_start"
    const val ACCESSIBILITY = "accessibility"
}

val LocalNavController = staticCompositionLocalOf<NavHostController> { error("No NavController provided") }

/** Go to [route] and drop the back stack up to (but not including) the start screen. */
fun NavHostController.forward(route: String) = navigate(route) { launchSingleTop = true }

/** Back to the start screen with an empty back stack (after a wipe). */
fun NavHostController.toStart(startRoute: String) = navigate(startRoute) {
    popUpTo(graph.id) { inclusive = true }
    launchSingleTop = true
}
