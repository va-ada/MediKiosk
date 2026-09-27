package org.neural.medikiosk.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Flip
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import org.neural.medikiosk.R
import org.neural.medikiosk.ui.theme.MinTouch
import kotlin.math.hypot

/** Tappable body regions → `body_part` (values match the joint-pain `jp_site` choices). */
private data class Region(val part: String, val points: List<Offset>, val back: Boolean)

private val REGIONS = listOf(
    Region("shoulder", listOf(Offset(0.33f, 0.21f), Offset(0.67f, 0.21f)), back = false),
    Region("hands", listOf(Offset(0.18f, 0.52f), Offset(0.82f, 0.52f)), back = false),
    Region("hip", listOf(Offset(0.41f, 0.52f), Offset(0.59f, 0.52f)), back = false),
    Region("knee", listOf(Offset(0.41f, 0.74f), Offset(0.59f, 0.74f)), back = false),
    Region("shoulder", listOf(Offset(0.33f, 0.21f), Offset(0.67f, 0.21f)), back = true),
    Region("back", listOf(Offset(0.5f, 0.42f)), back = true),
    Region("hip", listOf(Offset(0.41f, 0.52f), Offset(0.59f, 0.52f)), back = true),
    Region("knee", listOf(Offset(0.41f, 0.74f), Offset(0.59f, 0.74f)), back = true),
)

val BODY_PARTS = listOf("knee", "hip", "shoulder", "back", "hands")

fun bodyPartLabel(part: String): Int = when (part) {
    "knee" -> R.string.part_knee
    "hip" -> R.string.part_hip
    "shoulder" -> R.string.part_shoulder
    "back" -> R.string.part_back
    else -> R.string.part_hands
}

/**
 * Simple front/back body outline with tappable joints, plus the same parts as word+icon chips
 * (never rely on the picture alone).
 */
@Composable
fun BodyMap(selected: String?, onSelect: (String) -> Unit, modifier: Modifier = Modifier) {
    var backView by rememberSaveable { mutableStateOf(false) }
    val scheme = MaterialTheme.colorScheme
    val regions = REGIONS.filter { it.back == backView }

    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            FilterChip(selected = !backView, onClick = { backView = false }, label = { Text(tr(R.string.body_front)) },
                leadingIcon = { androidx.compose.material3.Icon(Icons.Filled.Flip, null) }, modifier = Modifier.heightIn(min = MinTouch))
            FilterChip(selected = backView, onClick = { backView = true }, label = { Text(tr(R.string.body_back)) },
                leadingIcon = { androidx.compose.material3.Icon(Icons.Filled.Flip, null) }, modifier = Modifier.heightIn(min = MinTouch))
        }
        Canvas(
            Modifier.fillMaxWidth(0.75f).aspectRatio(0.62f).pointerInput(backView) {
                detectTapGestures { tap ->
                    val w = size.width.toFloat(); val h = size.height.toFloat()
                    val hit = regions.flatMap { r -> r.points.map { r.part to it } }
                        .minByOrNull { (_, p) -> hypot(p.x * w - tap.x, p.y * h - tap.y) }
                        ?.takeIf { (_, p) -> hypot(p.x * w - tap.x, p.y * h - tap.y) < w * 0.14f }
                    hit?.let { onSelect(it.first) }
                }
            },
        ) {
            val w = size.width; val h = size.height
            fun o(x: Float, y: Float) = Offset(x * w, y * h)
            val line = Stroke(width = w * 0.07f, cap = StrokeCap.Round)
            val body = scheme.outline
            drawCircle(body, radius = w * 0.08f, center = o(0.5f, 0.08f), style = Stroke(w * 0.03f))
            drawLine(body, o(0.5f, 0.15f), o(0.5f, 0.18f), strokeWidth = w * 0.05f)
            drawRoundRect(body, topLeft = o(0.34f, 0.18f), size = androidx.compose.ui.geometry.Size(0.32f * w, 0.34f * h),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(w * 0.06f), style = Stroke(w * 0.03f))
            drawLine(body, o(0.33f, 0.21f), o(0.18f, 0.50f), strokeWidth = line.width, cap = StrokeCap.Round)
            drawLine(body, o(0.67f, 0.21f), o(0.82f, 0.50f), strokeWidth = line.width, cap = StrokeCap.Round)
            drawLine(body, o(0.42f, 0.52f), o(0.40f, 0.95f), strokeWidth = line.width, cap = StrokeCap.Round)
            drawLine(body, o(0.58f, 0.52f), o(0.60f, 0.95f), strokeWidth = line.width, cap = StrokeCap.Round)
            if (backView) drawLine(body, o(0.5f, 0.2f), o(0.5f, 0.5f), strokeWidth = w * 0.02f)
            regions.forEach { r ->
                r.points.forEach { p ->
                    val on = r.part == selected
                    drawCircle(if (on) scheme.secondary else scheme.primary.copy(alpha = 0.25f), radius = w * 0.075f, center = o(p.x, p.y))
                    drawCircle(scheme.primary, radius = w * 0.075f, center = o(p.x, p.y), style = Stroke(w * 0.012f))
                }
            }
        }
        val parts = if (backView) listOf("back", "shoulder", "hip", "knee") else listOf("knee", "hip", "shoulder", "hands")
        Grid(parts, columns = 2) { part, m ->
            IconTile(tr(bodyPartLabel(part)), contentIcon(part), { onSelect(part) }, m, selected = part == selected, iconSize = 32.dp)
        }
    }
}
