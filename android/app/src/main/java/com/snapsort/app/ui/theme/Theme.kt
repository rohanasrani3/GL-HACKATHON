package com.snapsort.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val RelayColorScheme = darkColorScheme(
    primary = RelayGreen,
    onPrimary = RelayBackground,
    secondary = RelayLogoLime,
    onSecondary = RelayBackground,
    tertiary = RelayAmber,
    onTertiary = RelayBackground,
    background = RelayBackground,
    onBackground = RelayTextPrimary,
    surface = RelaySurface,
    onSurface = RelayTextPrimary,
    surfaceVariant = RelaySurface,
    onSurfaceVariant = RelayTextMuted,
    outline = RelayBorder,
    error = RelayAmber,
    onError = RelayBackground,
)

@Composable
fun LaterRelayTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = RelayColorScheme,
        typography = RelayTypography,
        content = content,
    )
}
