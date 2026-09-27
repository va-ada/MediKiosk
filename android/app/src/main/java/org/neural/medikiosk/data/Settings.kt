package org.neural.medikiosk.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import org.neural.medikiosk.net.DeviceMode

private val Context.store: DataStore<Preferences> by preferencesDataStore(name = "device_settings")

/** Device configuration only — never patient data (the kiosk keeps nothing about patients, rule 10). */
data class DeviceSettings(
    val serverUrl: String = "http://192.168.2.1:8000",
    val relayUrl: String = "http://192.168.2.1:8003",
    val deviceId: String = "KIOSK-01",
    val deviceMode: String = DeviceMode.KIOSK,
    val defaultLanguage: String = "hi",
    val highContrast: Boolean = false,
    val largeText: Boolean = false,
    val slowPrompts: Boolean = false,
    val handsetMode: Boolean = false,
)

class SettingsRepository(private val context: Context) {
    private object Keys {
        val server = stringPreferencesKey("server_url")
        val relay = stringPreferencesKey("relay_url")
        val deviceId = stringPreferencesKey("device_id")
        val mode = stringPreferencesKey("device_mode")
        val language = stringPreferencesKey("default_language")
        val highContrast = booleanPreferencesKey("high_contrast")
        val largeText = booleanPreferencesKey("large_text")
        val slowPrompts = booleanPreferencesKey("slow_prompts")
        val handset = booleanPreferencesKey("handset_mode")
    }

    val settings: Flow<DeviceSettings> = context.store.data.map { p ->
        val d = DeviceSettings()
        DeviceSettings(
            serverUrl = p[Keys.server] ?: d.serverUrl,
            relayUrl = p[Keys.relay] ?: d.relayUrl,
            deviceId = p[Keys.deviceId] ?: d.deviceId,
            deviceMode = p[Keys.mode] ?: d.deviceMode,
            defaultLanguage = p[Keys.language] ?: d.defaultLanguage,
            highContrast = p[Keys.highContrast] ?: d.highContrast,
            largeText = p[Keys.largeText] ?: d.largeText,
            slowPrompts = p[Keys.slowPrompts] ?: d.slowPrompts,
            handsetMode = p[Keys.handset] ?: d.handsetMode,
        )
    }

    suspend fun save(s: DeviceSettings) {
        context.store.edit { p ->
            p[Keys.server] = s.serverUrl.trim()
            p[Keys.relay] = s.relayUrl.trim()
            p[Keys.deviceId] = s.deviceId.trim().uppercase()
            p[Keys.mode] = s.deviceMode
            p[Keys.language] = s.defaultLanguage
            p[Keys.highContrast] = s.highContrast
            p[Keys.largeText] = s.largeText
            p[Keys.slowPrompts] = s.slowPrompts
            p[Keys.handset] = s.handsetMode
        }
    }
}
