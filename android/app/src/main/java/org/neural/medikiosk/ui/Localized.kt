package org.neural.medikiosk.ui

import android.content.Context
import android.content.res.Configuration
import android.content.res.Resources
import androidx.annotation.StringRes
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.platform.LocalContext
import java.util.Locale

/** The patient's chosen language (`hi` | `en`) — independent of the phone's system locale. */
val LocalLang = staticCompositionLocalOf { "hi" }

fun localizedResources(context: Context, lang: String): Resources {
    val config = Configuration(context.resources.configuration).apply { setLocale(Locale.forLanguageTag(lang)) }
    return context.createConfigurationContext(config).resources
}

/** A string resource in the patient's language (values/ = English, values-hi/ = Hindi). */
@Composable
fun tr(@StringRes id: Int, vararg args: Any): String = trIn(LocalLang.current, id, *args)

/** A string resource in an explicit language (e.g. bilingual labels before a language is chosen). */
@Composable
fun trIn(lang: String, @StringRes id: Int, vararg args: Any): String {
    val context = LocalContext.current
    val res = remember(context, lang) { localizedResources(context, lang) }
    return if (args.isEmpty()) res.getString(id) else res.getString(id, *args)
}

/** Pick the hi or en text of a content label. */
fun pick(lang: String, hi: String?, en: String?): String = (if (lang == "hi") hi else en) ?: en ?: hi ?: ""
