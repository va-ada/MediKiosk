package org.neural.medikiosk

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import org.neural.medikiosk.data.DeviceSettings
import org.neural.medikiosk.data.KioskRepository
import org.neural.medikiosk.data.SettingsRepository
import org.neural.medikiosk.net.Patient
import org.neural.medikiosk.net.QueueItem
import org.neural.medikiosk.net.Session

/**
 * Activity-scoped state of one patient's intake (CLAUDE.md §8: one ViewModel per flow).
 * Everything patient-related lives here, in memory only, so [clear] is the whole kiosk wipe (rule 10, §10.9).
 */
class IntakeViewModel(app: Application) : AndroidViewModel(app) {
    val settingsRepo = SettingsRepository(app)

    /** Device settings (null until DataStore has loaded once). */
    val settings: StateFlow<DeviceSettings?> = settingsRepo.settings.stateIn(viewModelScope, SharingStarted.Eagerly, null)

    val repo = KioskRepository { settings.value ?: DeviceSettings() }

    var language by mutableStateOf("hi")
    var patient by mutableStateOf<Patient?>(null)
    var session by mutableStateOf<Session?>(null)
    var token by mutableStateOf<QueueItem?>(null)

    /** Forget the patient: memory state and every cache file (photos, voice clips, QR images). */
    fun clear() {
        language = settings.value?.defaultLanguage ?: "hi"
        patient = null
        session = null
        token = null
        wipeCacheFiles()
    }

    private fun wipeCacheFiles() {
        val app = getApplication<Application>()
        listOfNotNull(app.cacheDir, app.externalCacheDir).forEach { dir -> dir.listFiles()?.forEach { it.deleteRecursively() } }
    }
}
