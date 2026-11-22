package dk.bjarkebjarke.tally

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import io.kotest.matchers.comparables.shouldBeGreaterThan
import io.kotest.matchers.comparables.shouldBeLessThan
import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test

class ThemeTest {
    @Test
    fun darkThemeUsesDarkScheme() {
        val scheme = colorSchemeFor(darkTheme = true)
        scheme.background shouldBe Color(0xFF0F1415) // Petrol dark surface, not the Material purple baseline
        scheme.background.luminance() shouldBeLessThan 0.2f
        scheme.onBackground.luminance() shouldBeGreaterThan 0.5f
    }

    @Test
    fun lightThemeUsesLightScheme() {
        val scheme = colorSchemeFor(darkTheme = false)
        scheme.background shouldBe Color(0xFFF6FAFB) // Petrol light surface, not the Material purple baseline
        scheme.background.luminance() shouldBeGreaterThan 0.8f
        scheme.onBackground.luminance() shouldBeLessThan 0.2f
    }
}
