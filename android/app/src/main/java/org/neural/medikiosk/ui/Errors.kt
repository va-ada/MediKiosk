package org.neural.medikiosk.ui

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import org.neural.medikiosk.R
import org.neural.medikiosk.ui.theme.Red

/** Friendly patient-facing text for a §1 error code. */
fun errorMessageRes(code: String): Int = when (code) {
    "invalid_otp" -> R.string.err_invalid_otp
    "abha_not_found" -> R.string.err_abha_not_found
    "invalid_abha" -> R.string.err_invalid_abha
    "consent_required" -> R.string.err_consent_required
    "nlp_unavailable" -> R.string.err_nlp_unavailable
    "network_error" -> R.string.err_network
    "validation_error" -> R.string.err_validation
    "not_found" -> R.string.err_not_found
    "invalid_state" -> R.string.err_invalid_state
    "forbidden" -> R.string.err_forbidden
    "too_large" -> R.string.err_too_large
    else -> R.string.err_unknown
}

/** A red message card for a failed call (nothing shown when [code] is null). */
@Composable
fun ErrorCard(code: String?, modifier: Modifier = Modifier) {
    if (code == null) return
    Card(
        modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = Red, contentColor = Color.White),
    ) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.ErrorOutline, contentDescription = null, modifier = Modifier.size(36.dp))
            Spacer(Modifier.width(12.dp))
            Text(tr(errorMessageRes(code)), style = MaterialTheme.typography.bodyLarge)
        }
    }
}
