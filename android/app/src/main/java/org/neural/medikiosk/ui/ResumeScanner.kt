package org.neural.medikiosk.ui

import android.Manifest
import android.content.Context
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Log
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.LuminanceSource
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.RGBLuminanceSource
import com.google.zxing.common.HybridBinarizer
import com.google.zxing.qrcode.QRCodeReader
import kotlinx.coroutines.launch
import org.neural.medikiosk.IntakeViewModel
import org.neural.medikiosk.R
import org.neural.medikiosk.data.errorCode
import org.neural.medikiosk.net.ApiClient
import org.neural.medikiosk.net.Session
import org.neural.medikiosk.net.TokenQr
import java.io.File
import java.util.concurrent.Executors

/** ZXing QR decode of a luminance source (camera frame or bitmap); null when no QR is found. */
fun decodeQr(source: LuminanceSource): String? = try {
    QRCodeReader().decode(BinaryBitmap(HybridBinarizer(source)), mapOf(DecodeHintType.TRY_HARDER to true)).text
} catch (_: Exception) {
    null
}

fun decodeQr(bitmap: Bitmap): String? {
    val px = IntArray(bitmap.width * bitmap.height)
    bitmap.getPixels(px, 0, bitmap.width, 0, 0, bitmap.width, bitmap.height)
    return decodeQr(RGBLuminanceSource(bitmap.width, bitmap.height, px))
}

/** The token QR payload (§10.9), or null if the text is something else. */
fun parseTokenQr(text: String): TokenQr? = runCatching { ApiClient.json.decodeFromString(TokenQr.serializer(), text.trim()) }.getOrNull()

/** Debug-only test hook: a QR image pushed to the app's external files dir (never present on a real kiosk). */
fun debugFile(context: Context, name: String): File? {
    val debuggable = context.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
    return context.getExternalFilesDir("debug")?.resolve(name)?.takeIf { debuggable && it.exists() }
}

/**
 * "Continue with my token": scan the token slip's QR (CameraX + ZXing) → `GET /api/sessions/{id}` →
 * [onResumed] with the session (the caller routes by status). Absent tokens are reactivated.
 */
@Composable
fun ResumeScanner(vm: IntakeViewModel, onResumed: (Session) -> Unit, onBack: () -> Unit) {
    val context = LocalContext.current
    var granted by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted = it }
    LaunchedEffect(Unit) { if (!granted) ask.launch(Manifest.permission.CAMERA) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var badCode by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val debugQr = remember { debugFile(context, "qr.png") }

    fun resume(text: String) {
        if (busy) return
        val qr = parseTokenQr(text)
        if (qr == null) { badCode = true; return }
        busy = true; error = null; badCode = false
        scope.launch {
            val s = vm.repo.call { session(qr.sessionId) }
            val p = s.getOrNull()?.let { vm.repo.call { patient(it.patientId) } }
            val t = vm.repo.call { reactivate(qr.tokenId) }  // only succeeds for an `absent` token; otherwise ignored
            busy = false
            val session = s.getOrNull()
            if (session == null) { error = s.errorCode(); return@launch }
            vm.clear()
            vm.session = session
            p?.getOrNull()?.let { vm.patient = it; vm.language = it.language }
            vm.token = t.getOrNull()
            onResumed(session)
        }
    }

    KioskScaffold(audioKey = null, speech = tr(R.string.resume_hint)) {
        ScreenBody {
            Heading(tr(R.string.resume_title))
            Text(tr(R.string.resume_hint), style = MaterialTheme.typography.bodyLarge, textAlign = TextAlign.Center)
            if (badCode) ErrorCard("validation_error")
            ErrorCard(error)
            if (busy) CircularProgressIndicator()
            if (granted) {
                QrCamera(onText = { text -> scope.launch { resume(text) } }, Modifier.fillMaxWidth().aspectRatio(1f))
            } else {
                BigButton(tr(R.string.resume_allow_camera), Icons.Filled.CameraAlt, { ask.launch(Manifest.permission.CAMERA) }, Modifier.fillMaxWidth())
            }
            if (debugQr != null) {
                BigOutlinedButton("DEBUG: ${debugQr.name}", Icons.Filled.BugReport, {
                    val text = BitmapFactory.decodeFile(debugQr.path)?.let(::decodeQr)
                    Log.i("MediKiosk", "debug QR decoded: $text")
                    if (text == null) badCode = true else resume(text)
                }, Modifier.fillMaxWidth())
            }
            BigOutlinedButton(tr(R.string.back), Icons.AutoMirrored.Filled.ArrowBack, onBack, Modifier.fillMaxWidth())
        }
    }
}

/** Back-camera preview that reports the first decoded QR text (then keeps scanning until the screen leaves). */
@Composable
private fun QrCamera(onText: (String) -> Unit, modifier: Modifier) {
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val executor = remember { Executors.newSingleThreadExecutor() }
    var last by remember { mutableStateOf<String?>(null) }
    val previewView = remember { PreviewView(context) }
    DisposableEffect(owner) {
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            val provider = future.get()
            val preview = Preview.Builder().build().also { it.surfaceProvider = previewView.surfaceProvider }
            val analysis = ImageAnalysis.Builder().setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST).build()
            analysis.setAnalyzer(executor) { image ->
                val plane = image.planes[0]
                val bytes = ByteArray(plane.buffer.remaining()).also { plane.buffer.get(it) }
                val text = decodeQr(PlanarYUVLuminanceSource(bytes, plane.rowStride, image.height, 0, 0, image.width, image.height, false))
                image.close()
                if (text != null && text != last) {
                    last = text
                    ContextCompat.getMainExecutor(context).execute { onText(text) }
                }
            }
            runCatching {
                provider.unbindAll()
                provider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
            }.onFailure { Log.w("MediKiosk", "camera: ${it.message}") }
        }, ContextCompat.getMainExecutor(context))
        onDispose {
            runCatching { future.get().unbindAll() }
            executor.shutdown()
        }
    }
    Box(modifier.clip(RoundedCornerShape(16.dp)).border(BorderStroke(4.dp, MaterialTheme.colorScheme.primary), RoundedCornerShape(16.dp))) {
        AndroidView({ previewView }, Modifier.fillMaxSize())
        Box(Modifier.fillMaxSize().padding(48.dp).border(3.dp, Color.White, RoundedCornerShape(12.dp)), contentAlignment = Alignment.Center) {}
    }
}
