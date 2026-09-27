package org.neural.medikiosk.audio

import androidx.compose.runtime.staticCompositionLocalOf

/**
 * Plays a pre-rendered prompt (`content/audio/{lang}/{key}.wav`, CONTRACTS.md §9.7).
 * Key = question id, triage slot or system phrase (`sys_welcome`, …).
 */
interface AudioPrompter {
    fun play(key: String, lang: String)
    fun stop()

    /** Speak text that has no recorded prompt (text-to-speech). */
    fun speak(text: String, lang: String) = Unit

    /** Stop only if [key] (or `tts:<text>`) is what is playing — a screen leaving must not cut the next screen's prompt. */
    fun stopIfPlaying(key: String) = stop()
}

/** Silent stand-in (tests, previews). */
object NoopAudioPrompter : AudioPrompter {
    override fun play(key: String, lang: String) = Unit
    override fun stop() = Unit
}

val LocalAudioPrompter = staticCompositionLocalOf<AudioPrompter> { NoopAudioPrompter }
