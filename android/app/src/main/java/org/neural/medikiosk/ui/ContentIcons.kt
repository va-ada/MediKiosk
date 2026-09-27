package org.neural.medikiosk.ui

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.automirrored.filled.DirectionsRun
import androidx.compose.material.icons.automirrored.filled.DirectionsWalk
import androidx.compose.material.icons.automirrored.filled.HelpOutline
import androidx.compose.material.icons.automirrored.filled.TrendingUp
import androidx.compose.material.icons.filled.AcUnit
import androidx.compose.material.icons.filled.Accessibility
import androidx.compose.material.icons.filled.AccessibilityNew
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Air
import androidx.compose.material.icons.filled.AirlineSeatReclineNormal
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.Block
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Chair
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Circle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Construction
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.DragHandle
import androidx.compose.material.icons.filled.Eco
import androidx.compose.material.icons.filled.Egg
import androidx.compose.material.icons.filled.Event
import androidx.compose.material.icons.filled.EventBusy
import androidx.compose.material.icons.filled.Face
import androidx.compose.material.icons.filled.Fastfood
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.FrontHand
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.Healing
import androidx.compose.material.icons.filled.Hotel
import androidx.compose.material.icons.filled.Icecream
import androidx.compose.material.icons.filled.LocalDrink
import androidx.compose.material.icons.filled.LocalFireDepartment
import androidx.compose.material.icons.filled.Masks
import androidx.compose.material.icons.filled.Medication
import androidx.compose.material.icons.filled.MonitorHeart
import androidx.compose.material.icons.filled.Mood
import androidx.compose.material.icons.filled.MoreHoriz
import androidx.compose.material.icons.filled.NightsStay
import androidx.compose.material.icons.filled.Psychology
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material.icons.filled.Restaurant
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.SetMeal
import androidx.compose.material.icons.filled.SoupKitchen
import androidx.compose.material.icons.filled.SportsGymnastics
import androidx.compose.material.icons.filled.Stairs
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material.icons.filled.Thermostat
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material.icons.filled.Today
import androidx.compose.material.icons.filled.Umbrella
import androidx.compose.material.icons.filled.Watch
import androidx.compose.material.icons.filled.Waves
import androidx.compose.material.icons.filled.Wc
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material.icons.filled.Whatshot
import androidx.compose.ui.graphics.vector.ImageVector

/**
 * Picture for a content `icon` name (content/triage.yaml complaints, content/questions YAML choices).
 * Every choice is shown with icon + words (CLAUDE.md §7); unknown names get a neutral dot.
 */
fun contentIcon(name: String?): ImageVector {
    val n = name.orEmpty()
    return when {
        // triage complaints
        n == "joint" -> Icons.Filled.AccessibilityNew
        n == "fever" -> Icons.Filled.Thermostat
        n == "cough" -> Icons.Filled.Masks
        n == "stomach" -> Icons.Filled.Restaurant
        n == "headache" -> Icons.Filled.Psychology
        n == "chest" -> Icons.Filled.MonitorHeart
        n == "breathing" -> Icons.Filled.Air
        n == "skin" -> Icons.Filled.FrontHand
        n == "other" -> Icons.Filled.MoreHoriz
        // body parts
        n == "knee" || n == "ankle" -> Icons.AutoMirrored.Filled.DirectionsWalk
        n == "back" -> Icons.Filled.AirlineSeatReclineNormal
        n == "hip" -> Icons.Filled.Accessibility
        n == "shoulder" -> Icons.Filled.SportsGymnastics
        n == "hands" -> Icons.Filled.FrontHand
        n == "wrist" -> Icons.Filled.Watch
        n == "elbow" -> Icons.Filled.FitnessCenter
        n == "neck" -> Icons.Filled.Face
        // answers
        n == "yes" -> Icons.Filled.Check
        n == "no" -> Icons.Filled.Close
        n == "none" -> Icons.Filled.Block
        n == "not_sure" -> Icons.AutoMirrored.Filled.HelpOutline
        n == "side_left" -> Icons.AutoMirrored.Filled.ArrowBack
        n == "side_right" -> Icons.AutoMirrored.Filled.ArrowForward
        n == "side_both" -> Icons.Filled.SwapHoriz
        n == "days" || n == "daily" -> Icons.Filled.Today
        n == "weeks" || n == "weekly" -> Icons.Filled.DateRange
        n == "months" -> Icons.Filled.CalendarMonth
        n == "years" -> Icons.Filled.Event
        n == "rarely" -> Icons.Filled.EventBusy
        n == "sudden" -> Icons.Filled.Bolt
        n == "gradual" -> Icons.AutoMirrored.Filled.TrendingUp
        n == "ache" -> Icons.Filled.Waves
        n == "sharp" -> Icons.Filled.Bolt
        n == "burning" || n == "acidity" || n == "chilli" -> Icons.Filled.LocalFireDepartment
        n == "throbbing" -> Icons.Filled.GraphicEq
        n == "stairs" -> Icons.Filled.Stairs
        n == "walking" || n.startsWith("walk_") -> Icons.AutoMirrored.Filled.DirectionsWalk
        n == "movement" -> Icons.AutoMirrored.Filled.DirectionsRun
        n == "cold" || n == "snow" -> Icons.Filled.AcUnit
        n == "rest" -> Icons.Filled.Hotel
        n == "morning" || n == "sun" -> Icons.Filled.WbSunny
        n == "heat" || n == "warm_food" -> Icons.Filled.Whatshot
        n == "medicine" -> Icons.Filled.Medication
        n == "rain" -> Icons.Filled.Umbrella
        n == "fried" -> Icons.Filled.Fastfood
        n == "milk" || n == "cold_drink" -> Icons.Filled.LocalDrink
        n == "curd" -> Icons.Filled.Icecream
        n == "sour" -> Icons.Filled.SoupKitchen
        n == "egg" -> Icons.Filled.Egg
        n == "veg" -> Icons.Filled.Eco
        n == "non_veg" -> Icons.Filled.SetMeal
        n == "food" || n.startsWith("appetite") -> Icons.Filled.Restaurant
        n == "gas" -> Icons.Filled.Air
        n == "heavy" || n == "heavy_work" -> Icons.Filled.Construction
        n.startsWith("bowel") || n.startsWith("stool") -> Icons.Filled.Wc
        n.startsWith("sleep") -> Icons.Filled.Bedtime
        n == "late_night" -> Icons.Filled.NightsStay
        n.startsWith("frame") -> Icons.Filled.Accessibility
        n.startsWith("mood") || n == "stress" -> Icons.Filled.Mood
        n.startsWith("skin") -> Icons.Filled.Healing
        n == "clock_long" -> Icons.Filled.Schedule
        n == "clock_short" -> Icons.Filled.Timer
        n == "sitting" -> Icons.Filled.Chair
        n == "less" -> Icons.Filled.Remove
        n == "more" -> Icons.Filled.Add
        n == "same" -> Icons.Filled.DragHandle
        else -> Icons.Filled.Circle
    }
}
