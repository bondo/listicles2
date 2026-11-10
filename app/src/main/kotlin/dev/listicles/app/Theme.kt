package dev.listicles.app

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

/** Static schemes (no dynamic color) so screenshots and contrast checks are deterministic. */
fun colorSchemeFor(darkTheme: Boolean): ColorScheme = if (darkTheme) darkColorScheme() else lightColorScheme()

@Composable
fun ListiclesTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(colorScheme = colorSchemeFor(darkTheme), content = content)
}
