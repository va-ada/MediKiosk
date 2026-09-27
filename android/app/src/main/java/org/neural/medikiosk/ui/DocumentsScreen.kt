package org.neural.medikiosk.ui

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Log
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.AddAPhoto
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.DoNotDisturb
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.neural.medikiosk.IntakeViewModel
import org.neural.medikiosk.R
import org.neural.medikiosk.data.errorCode
import org.neural.medikiosk.data.uploadDocument
import java.io.File
import java.util.UUID

private enum class DocStep { INTRO, CAMERA, REVIEW, SENDING, SENT }

private const val MAX_UPLOAD_BYTES = 9_500_000  // server limit is 10 MB (§4.4)

/** Downscale a JPEG in place until it is under the upload limit. */
private fun shrinkIfNeeded(file: File) {
    var sample = 2
    while (file.length() > MAX_UPLOAD_BYTES && sample <= 8) {
        val bmp = BitmapFactory.decodeFile(file.path, BitmapFactory.Options().apply { inSampleSize = sample }) ?: return
        file.outputStream().use { bmp.compress(Bitmap.CompressFormat.JPEG, 88, it) }
        bmp.recycle()
        sample *= 2
    }
}

private fun thumbnail(path: String): Bitmap? =
    BitmapFactory.decodeFile(path, BitmapFactory.Options().apply { inSampleSize = 8 })

/**
 * Documents (journey step 5): photograph old reports page by page (CameraX, document frame), review thumbnails
 * (delete / retake / add another page), upload each page (`page_no`) with progress, then delete the local
 * images. "I have no papers" skips to read-back. Photos live only in the cache dir (wiped with the session).
 */
@Composable
fun DocumentsScreen(vm: IntakeViewModel, onDone: () -> Unit) {
    val session = vm.session ?: return
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var step by rememberSaveable { mutableStateOf(if (vm.docPages.isEmpty()) DocStep.INTRO else DocStep.REVIEW) }
    var error by remember { mutableStateOf<String?>(null) }
    var sentCount by remember { mutableIntStateOf(0) }
    var statuses by remember { mutableStateOf<List<String>>(emptyList()) }
    val debugDoc = remember { debugFile(context, "doc.png") ?: debugFile(context, "doc.jpg") }
    var granted by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted = it; if (it) step = DocStep.CAMERA }

    fun openCamera() { if (granted) step = DocStep.CAMERA else ask.launch(Manifest.permission.CAMERA) }
    BackHandler(enabled = step == DocStep.CAMERA || step == DocStep.REVIEW) {
        step = if (step == DocStep.CAMERA && vm.docPages.isNotEmpty()) DocStep.REVIEW else DocStep.INTRO
    }

    fun upload() {
        step = DocStep.SENDING; error = null; sentCount = 0
        scope.launch {
            val ids = mutableListOf<String>()
            for ((i, path) in vm.docPages.toList().withIndex()) {
                val file = File(path)
                val r = vm.repo.uploadDocument(session.id, i + 1, file)
                if (r.isFailure) { error = r.errorCode(); step = DocStep.REVIEW; return@launch }
                ids += r.getOrThrow().id
                file.delete()  // never keep a patient's photo on the kiosk once the server has it
                sentCount = i + 1
            }
            vm.docPages.clear()
            step = DocStep.SENT
            // Show whether each page was read (OCR runs on the server in the background).
            repeat(15) {
                statuses = ids.map { id -> vm.repo.call { document(id) }.getOrNull()?.status ?: "pending" }
                if (statuses.none { it == "pending" }) return@launch
                delay(2000)
            }
        }
    }

    KioskScaffold(audioKey = null, speech = tr(if (step == DocStep.CAMERA) R.string.docs_place_paper else R.string.docs_question)) {
        ScreenBody {
            ErrorCard(error)
            when (step) {
                DocStep.INTRO -> {
                    Heading(tr(R.string.docs_question))
                    Text(tr(R.string.docs_explain), style = MaterialTheme.typography.bodyLarge, textAlign = TextAlign.Center)
                    BigButton(tr(R.string.docs_take_photo), Icons.Filled.PhotoCamera, ::openCamera, Modifier.fillMaxWidth(), minHeight = 110.dp)
                    BigOutlinedButton(tr(R.string.docs_no_papers), Icons.Filled.DoNotDisturb, onDone, Modifier.fillMaxWidth())
                    if (debugDoc != null) DebugAddPage(debugDoc, vm) { step = DocStep.REVIEW }
                }
                DocStep.CAMERA -> {
                    Heading(tr(R.string.docs_place_paper))
                    DocumentCamera(onCaptured = { f -> vm.docPages.add(f.path); step = DocStep.REVIEW }, onError = { error = "unknown_error" })
                    if (debugDoc != null) DebugAddPage(debugDoc, vm) { step = DocStep.REVIEW }
                }
                DocStep.REVIEW -> {
                    Heading(tr(R.string.docs_pages, vm.docPages.size))
                    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        vm.docPages.toList().forEachIndexed { i, path ->
                            PageThumb(i + 1, path, onDelete = { File(path).delete(); vm.docPages.remove(path); if (vm.docPages.isEmpty()) step = DocStep.INTRO },
                                onRetake = { File(path).delete(); vm.docPages.remove(path); openCamera() })
                        }
                    }
                    BigOutlinedButton(tr(R.string.docs_add_page), Icons.Filled.AddAPhoto, ::openCamera, Modifier.fillMaxWidth())
                    BigButton(tr(R.string.docs_send), Icons.Filled.CloudUpload, ::upload, Modifier.fillMaxWidth(), enabled = vm.docPages.isNotEmpty())
                    if (error == "forbidden") BigOutlinedButton(tr(R.string.docs_no_papers), Icons.Filled.DoNotDisturb, onDone, Modifier.fillMaxWidth())
                }
                DocStep.SENDING -> {
                    Heading(tr(R.string.docs_sending, sentCount + 1, vm.docPages.size))
                    LinearProgressIndicator(progress = { sentCount.toFloat() / vm.docPages.size.coerceAtLeast(1) }, modifier = Modifier.fillMaxWidth())
                    CircularProgressIndicator()
                }
                DocStep.SENT -> {
                    Heading(tr(R.string.docs_sent))
                    statuses.forEachIndexed { i, st ->
                        Text(tr(R.string.docs_page_status, i + 1, tr(when (st) {
                            "processed" -> R.string.docs_read
                            "failed" -> R.string.docs_not_read
                            else -> R.string.docs_reading
                        })), style = MaterialTheme.typography.bodyLarge)
                    }
                    BigOutlinedButton(tr(R.string.docs_add_page), Icons.Filled.AddAPhoto, ::openCamera, Modifier.fillMaxWidth())
                    BigButton(tr(R.string.next), Icons.AutoMirrored.Filled.ArrowForward, onDone, Modifier.fillMaxWidth())
                }
            }
        }
    }
}

@Composable
private fun PageThumb(n: Int, path: String, onDelete: () -> Unit, onRetake: () -> Unit) {
    val bmp = remember(path) { thumbnail(path)?.asImageBitmap() }
    Card(Modifier.width(170.dp), border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.padding(8.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(tr(R.string.docs_page_n, n), style = MaterialTheme.typography.titleLarge)
            if (bmp != null) Image(bmp, null, Modifier.fillMaxWidth().aspectRatio(0.72f).clip(RoundedCornerShape(8.dp)), contentScale = ContentScale.Crop)
            ThumbButton(tr(R.string.docs_retake), Icons.Filled.CameraAlt, onRetake)
            ThumbButton(tr(R.string.docs_delete), Icons.Filled.Delete, onDelete)
        }
    }
}

/** Compact thumbnail action: icon above the word so it never wraps mid-word. */
@Composable
private fun ThumbButton(text: String, icon: androidx.compose.ui.graphics.vector.ImageVector, onClick: () -> Unit) {
    androidx.compose.material3.OutlinedButton(onClick = onClick, modifier = Modifier.fillMaxWidth().heightIn(min = 72.dp),
        shape = RoundedCornerShape(12.dp), border = BorderStroke(2.dp, MaterialTheme.colorScheme.primary),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(4.dp)) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            androidx.compose.material3.Icon(icon, null, Modifier.size(28.dp))
            Text(text, style = MaterialTheme.typography.labelLarge, textAlign = TextAlign.Center)
        }
    }
}

/** Debug builds only: add a pushed sample image as a page (exercises the same upload path as a photo). */
@Composable
private fun DebugAddPage(src: File, vm: IntakeViewModel, onAdded: () -> Unit) {
    val context = LocalContext.current
    BigOutlinedButton("DEBUG: add ${src.name}", Icons.Filled.BugReport, {
        val copy = File(context.cacheDir, "doc_${UUID.randomUUID()}.${src.extension}")
        src.copyTo(copy)
        Log.i("MediKiosk", "DEBUG page added from ${src.name}")
        vm.docPages.add(copy.path); onAdded()
    }, Modifier.fillMaxWidth())
}

/** CameraX preview with a document frame and a big capture button; saves a JPEG into the cache dir. */
@Composable
private fun DocumentCamera(onCaptured: (File) -> Unit, onError: () -> Unit) {
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()
    val previewView = remember { PreviewView(context) }
    val capture = remember { ImageCapture.Builder().setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY).build() }
    var busy by remember { mutableStateOf(false) }
    DisposableEffect(owner) {
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            val provider = future.get()
            val preview = Preview.Builder().build().also { it.surfaceProvider = previewView.surfaceProvider }
            runCatching {
                provider.unbindAll()
                provider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, preview, capture)
            }.onFailure { Log.w("MediKiosk", "camera: ${it.message}") }
        }, ContextCompat.getMainExecutor(context))
        onDispose { runCatching { future.get().unbindAll() } }
    }
    Box(Modifier.fillMaxWidth().aspectRatio(0.75f).clip(RoundedCornerShape(16.dp))) {
        AndroidView({ previewView }, Modifier.fillMaxSize())
        Box(Modifier.fillMaxSize().padding(horizontal = 36.dp, vertical = 24.dp).border(4.dp, Color.White, RoundedCornerShape(8.dp)))
    }
    BigButton(tr(R.string.docs_capture), Icons.Filled.CameraAlt, {
        if (busy) return@BigButton
        busy = true
        val file = File(context.cacheDir, "doc_${UUID.randomUUID()}.jpg")
        capture.takePicture(ImageCapture.OutputFileOptions.Builder(file).build(), ContextCompat.getMainExecutor(context),
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    scope.launch {
                        withContext(Dispatchers.IO) { shrinkIfNeeded(file) }
                        busy = false
                        Log.i("MediKiosk", "captured page ${file.name} (${file.length()} bytes)")
                        onCaptured(file)
                    }
                }
                override fun onError(exception: ImageCaptureException) {
                    busy = false; file.delete()
                    Log.w("MediKiosk", "capture failed: ${exception.message}")
                    onError()
                }
            })
    }, Modifier.fillMaxWidth(), minHeight = 110.dp, enabled = !busy)
    if (busy) CircularProgressIndicator(Modifier.size(48.dp))
}
