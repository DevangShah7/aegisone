package com.aegisone.agent.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import android.os.Build

private val AegisOneBlue = Color(0xFF1F4ED8)
private val AegisOneBlueDark = Color(0xFF1E3A8A)
private val AegisOneSurfaceLight = Color(0xFFF8FAFC)
private val AegisOneSurfaceDark = Color(0xFF0B1220)

private val LightColors = lightColorScheme(
    primary = AegisOneBlue,
    onPrimary = Color.White,
    secondary = AegisOneBlueDark,
    background = AegisOneSurfaceLight,
    surface = AegisOneSurfaceLight,
    onSurface = Color(0xFF0B1220),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF93C5FD),
    onPrimary = AegisOneSurfaceDark,
    secondary = AegisOneBlue,
    background = AegisOneSurfaceDark,
    surface = AegisOneSurfaceDark,
    onSurface = Color(0xFFE2E8F0),
)

@Composable
fun AegisOneTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = true,
    content: @Composable () -> Unit,
) {
    val colors = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkColors
        else -> LightColors
    }

    MaterialTheme(
        colorScheme = colors,
        content = content,
    )
}