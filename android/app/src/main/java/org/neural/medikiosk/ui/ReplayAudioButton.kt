package org.neural.medikiosk.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.neural.medikiosk.R
import org.neural.medikiosk.audio.LocalAudioPrompter
import org.neural.medikiosk.ui.theme.MinTouch

/** "Listen again": replays the screen's recorded prompt [key] (or speaks [speech] when there is no recording). */
@Composable
fun ReplayAudioButton(key: String?, speech: String? = null, modifier: Modifier = Modifier) {
    val audio = LocalAudioPrompter.current
    val lang = LocalLang.current
    OutlinedButton(
        onClick = { if (key != null) audio.play(key, lang) else if (speech != null) audio.speak(speech, lang) },
        modifier = modifier.heightIn(min = MinTouch),
        shape = RoundedCornerShape(14.dp),
        border = BorderStroke(2.dp, MaterialTheme.colorScheme.primary),
    ) {
        Icon(Icons.AutoMirrored.Filled.VolumeUp, contentDescription = null, modifier = Modifier.size(30.dp))
        Spacer(Modifier.width(10.dp))
        Text(tr(R.string.listen_again), style = MaterialTheme.typography.labelLarge)
    }
}
