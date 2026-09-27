package org.neural.medikiosk.ui

import android.graphics.Bitmap
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.EditNote
import androidx.compose.material.icons.filled.NotificationsActive
import androidx.compose.material.icons.filled.QrCode2
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel
import org.neural.medikiosk.IntakeViewModel
import org.neural.medikiosk.R
import org.neural.medikiosk.net.ApiClient
import org.neural.medikiosk.net.QueueItem
import org.neural.medikiosk.net.TokenQr
import org.neural.medikiosk.ui.theme.Orange

/** The token QR payload (§10.9): exactly `{"session_id": "...", "token_id": "..."}`. */
fun tokenQrPayload(token: QueueItem): String = ApiClient.json.encodeToString(TokenQr.serializer(), TokenQr(token.sessionId, token.id))

/** Black-on-white QR bitmap (1 px per module; scaled up without smoothing when drawn). */
fun qrBitmap(text: String): Bitmap {
    val m = QRCodeWriter().encode(text, BarcodeFormat.QR_CODE, 0, 0,
        mapOf(EncodeHintType.MARGIN to 2, EncodeHintType.ERROR_CORRECTION to ErrorCorrectionLevel.M))
    val bmp = Bitmap.createBitmap(m.width, m.height, Bitmap.Config.ARGB_8888)
    for (y in 0 until m.height) for (x in 0 until m.width) {
        bmp.setPixel(x, y, if (m[x, y]) android.graphics.Color.BLACK else android.graphics.Color.WHITE)
    }
    return bmp
}

@Composable
fun QrImage(text: String, modifier: Modifier = Modifier) {
    val bmp = remember(text) { qrBitmap(text).asImageBitmap() }
    Image(bmp, contentDescription = null, filterQuality = FilterQuality.None,
        modifier = modifier.aspectRatio(1f).background(Color.White))
}

fun departmentLabel(dept: String?): Int = if (dept == "ayurveda") R.string.dept_ayurveda else R.string.dept_general

/** Big token number + department (shared by Token, Done and the patient-app status card). */
@Composable
fun TokenBadge(token: QueueItem, modifier: Modifier = Modifier) {
    Card(
        modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        border = BorderStroke(3.dp, MaterialTheme.colorScheme.primary),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(Modifier.fillMaxWidth().padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(tr(R.string.your_token), style = MaterialTheme.typography.titleLarge)
            Text(token.display, fontSize = 72.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            Text(tr(departmentLabel(token.department)), style = MaterialTheme.typography.bodyLarge)
        }
    }
}

/** Orange "a nurse has been informed" banner shown when triage raised alerts. */
@Composable
fun NurseInformedBanner() {
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = Orange, contentColor = Color.White)) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.NotificationsActive, null, Modifier.size(36.dp))
            Spacer(Modifier.width(12.dp))
            Text(tr(R.string.nurse_informed), style = MaterialTheme.typography.bodyLarge)
        }
    }
}

/**
 * Token (after triage): token number, department and the resume QR. Continue here → History;
 * continue at a hall station → large QR + instructions → Done. [statusCard] is the patient-app live card (A14).
 */
@Composable
fun TokenScreen(
    vm: IntakeViewModel,
    onContinueHere: () -> Unit,
    onFinishHere: () -> Unit,
    statusCard: (@Composable () -> Unit)? = null,
) {
    val token = vm.token ?: return
    var hallQr by rememberSaveable { mutableStateOf(false) }
    BackHandler { if (hallQr) hallQr = false }  // triage is done: never go back into it
    val payload = tokenQrPayload(token)

    KioskScaffold(audioKey = null) {
        ScreenBody {
            if (vm.triageAlerts.isNotEmpty()) NurseInformedBanner()
            if (!hallQr) {
                TokenBadge(token)
                statusCard?.invoke()
                QrImage(payload, Modifier.fillMaxWidth(0.5f))
                Text(tr(R.string.token_qr_hint), style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center)
                BigButton(tr(R.string.token_continue_here), Icons.Filled.EditNote, onContinueHere, Modifier.fillMaxWidth(), minHeight = 96.dp)
                BigOutlinedButton(tr(R.string.token_continue_hall), Icons.Filled.QrCode2, { hallQr = true }, Modifier.fillMaxWidth())
            } else {
                Heading(tr(R.string.token_hall_title, token.display))
                QrImage(payload, Modifier.fillMaxWidth(0.9f))
                Text(tr(R.string.token_hall_steps), style = MaterialTheme.typography.bodyLarge)
                BigButton(tr(R.string.done), Icons.Filled.Check, onFinishHere, Modifier.fillMaxWidth())
                BigOutlinedButton(tr(R.string.token_continue_here), Icons.AutoMirrored.Filled.ArrowForward, onContinueHere, Modifier.fillMaxWidth())
            }
        }
    }
}
