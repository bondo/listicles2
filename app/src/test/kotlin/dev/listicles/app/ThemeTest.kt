package dev.listicles.app

import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.graphics.luminance
import io.kotest.matchers.comparables.shouldBeGreaterThan
import io.kotest.matchers.comparables.shouldBeLessThan
import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test

class ThemeTest {
    @Test
    fun darkThemeUsesDarkScheme() {
        val scheme = colorSchemeFor(darkTheme = true)
        scheme.background shouldBe darkColorScheme().background
        scheme.background.luminance() shouldBeLessThan 0.2f
        scheme.onBackground.luminance() shouldBeGreaterThan 0.5f
    }

    @Test
    fun lightThemeUsesLightScheme() {
        val scheme = colorSchemeFor(darkTheme = false)
        scheme.background shouldBe lightColorScheme().background
        scheme.background.luminance() shouldBeGreaterThan 0.8f
        scheme.onBackground.luminance() shouldBeLessThan 0.2f
    }
}
