package org.neural.medikiosk.ui.theme

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

val Navy = Color(0xFF1F497D)
val Orange = Color(0xFFE07B24)
val Green = Color(0xFF1E8E6A)
val Red = Color(0xFFC0392B)

/** Accessibility rules (CLAUDE.md §7): touch targets ≥ 56 dp. */
val MinTouch = 56.dp

private val Light: ColorScheme = lightColorScheme(
    primary = Navy, onPrimary = Color.White, secondary = Orange, onSecondary = Color.White,
    tertiary = Green, error = Red, background = Color(0xFFF7F8FA), surface = Color.White,
    onBackground = Color(0xFF1A1A1A), onSurface = Color(0xFF1A1A1A),
)

/** High contrast: pure black background, white text, saturated yellow/cyan accents. */
private val HighContrast: ColorScheme = darkColorScheme(
    primary = Color(0xFFFFE000), onPrimary = Color.Black, secondary = Color(0xFF00E5FF), onSecondary = Color.Black,
    tertiary = Color(0xFF00E676), error = Color(0xFFFF5252), background = Color.Black, surface = Color.Black,
    onBackground = Color.White, onSurface = Color.White,
)

/** Body ≥ 20 sp, buttons (labelLarge) ≥ 24 sp; `scale` 1.3 in large-text mode. */
private fun typography(scale: Float) = Typography(
    displayLarge = TextStyle(fontSize = (56 * scale).sp, fontWeight = FontWeight.Bold),
    headlineLarge = TextStyle(fontSize = (34 * scale).sp, fontWeight = FontWeight.Bold, lineHeight = (42 * scale).sp),
    headlineMedium = TextStyle(fontSize = (28 * scale).sp, fontWeight = FontWeight.SemiBold, lineHeight = (36 * scale).sp),
    titleLarge = TextStyle(fontSize = (24 * scale).sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = TextStyle(fontSize = (22 * scale).sp, lineHeight = (30 * scale).sp),
    bodyMedium = TextStyle(fontSize = (20 * scale).sp, lineHeight = (28 * scale).sp),
    labelLarge = TextStyle(fontSize = (24 * scale).sp, fontWeight = FontWeight.SemiBold),
)

@Composable
fun MediKioskTheme(highContrast: Boolean = false, largeText: Boolean = false, content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (highContrast) HighContrast else Light,
        typography = typography(if (largeText) 1.3f else 1f),
        content = content,
    )
}
