package org.neural.medikiosk.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.PanTool
import androidx.compose.material.icons.filled.SupportAgent
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import org.neural.medikiosk.R
import org.neural.medikiosk.audio.LocalAudioPrompter
import org.neural.medikiosk.navigation.LocalNavController
import org.neural.medikiosk.navigation.Routes
import org.neural.medikiosk.ui.theme.Red

/**
 * Frame of every intake screen: a top bar with a large red **Emergency** button and **Need help**,
 * then the screen's content. Plays the screen's audio prompt ([audioKey]) on entry and stops it on leave.
 * [bilingual] shows the bar in Hindi + English (the Start screen, before a language is chosen).
 */
@Composable
fun KioskScaffold(
    audioKey: String?,
    modifier: Modifier = Modifier,
    bilingual: Boolean = false,
    showHelp: Boolean = true,
    content: @Composable ColumnScope.() -> Unit,
) {
    val nav = LocalNavController.current
    val lang = LocalLang.current
    val audio = LocalAudioPrompter.current
    if (audioKey != null) {
        LaunchedEffect(audioKey, lang) { audio.play(audioKey, lang) }
    }
    DisposableEffect(Unit) { onDispose { audio.stop() } }

    Column(modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().height(IntrinsicSize.Min).padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (showHelp) {
                TopBarButton(
                    text = if (bilingual) "${trIn("hi", R.string.need_help)} / ${trIn("en", R.string.need_help)}" else tr(R.string.need_help),
                    icon = Icons.Filled.PanTool,
                    onClick = { nav.navigate(Routes.HELP) { launchSingleTop = true } },
                    container = MaterialTheme.colorScheme.surface,
                    content = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.weight(1f),
                )
            } else {
                Box(Modifier.weight(1f))
            }
            TopBarButton(
                text = if (bilingual) "${trIn("hi", R.string.emergency)} / ${trIn("en", R.string.emergency)}" else tr(R.string.emergency),
                icon = Icons.Filled.Warning,
                onClick = { nav.navigate(Routes.EMERGENCY) { launchSingleTop = true } },
                container = Red,
                content = Color.White,
                modifier = Modifier.weight(1f),
            )
        }
        HorizontalDivider()
        Column(Modifier.fillMaxWidth().weight(1f), content = content)
    }
}

/** Top-bar action: icon above the words so long (bilingual) labels get the full button width. */
@Composable
private fun TopBarButton(text: String, icon: ImageVector, onClick: () -> Unit, container: Color, content: Color, modifier: Modifier) {
    Button(
        onClick = onClick,
        modifier = modifier.fillMaxHeight().heightIn(min = 88.dp),
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(2.dp, if (container == Red) Red else MaterialTheme.colorScheme.primary),
        colors = ButtonDefaults.buttonColors(containerColor = container, contentColor = content),
        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 6.dp),
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(icon, contentDescription = null, modifier = Modifier.size(32.dp))
            Text(text, style = MaterialTheme.typography.labelLarge, textAlign = TextAlign.Center)
        }
    }
}

/** "Need help" — full screen, a staff member will come. */
@Composable
fun NeedHelpScreen(onBack: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(32.dp, Alignment.CenterVertically),
    ) {
        Icon(Icons.Filled.SupportAgent, contentDescription = null, modifier = Modifier.size(120.dp), tint = MaterialTheme.colorScheme.primary)
        Text(tr(R.string.help_staff_coming), style = MaterialTheme.typography.headlineLarge, textAlign = TextAlign.Center)
        Text(tr(R.string.help_wait_here), style = MaterialTheme.typography.bodyLarge, textAlign = TextAlign.Center)
        BigButton(tr(R.string.back), Icons.AutoMirrored.Filled.ArrowBack, onBack, Modifier.fillMaxWidth())
    }
}
