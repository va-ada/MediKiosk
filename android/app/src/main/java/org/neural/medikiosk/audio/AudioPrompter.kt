package org.neural.medikiosk.audio

import androidx.compose.runtime.staticCompositionLocalOf

/**
 * Plays a pre-rendered prompt (`content/audio/{lang}/{key}.wav`, CONTRACTS.md §9.7).
 * Key = question id, triage slot or system phrase (`sys_welcome`, …).
 */
interface AudioPrompter {
    fun play(key: String, lang: String)
    fun stop()
}

/** Silent stand-in (tests, previews, and until A9). */
object NoopAudioPrompter : AudioPrompter {
    override fun play(key: String, lang: String) = Unit
    override fun stop() = Unit
}

val LocalAudioPrompter = staticCompositionLocalOf<AudioPrompter> { NoopAudioPrompter }
