package dk.bjarkebjarke.tally

import com.dropbox.differ.ImageComparator
import com.dropbox.differ.SimpleImageComparator
import io.kotest.matchers.shouldBe
import io.kotest.matchers.types.shouldBeInstanceOf
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * M1-03: the goldens are compared exactly. A single different pixel fails, and neither colour distance nor a shift is
 * forgiven. Robolectric because RoborazziOptions loads Android classes (a JUnit 4 test, run by the vintage engine).
 */
@RunWith(RobolectricTestRunner::class)
class ScreenshotOptionsTest {
    private val options = ScreenshotOptions.exact.compareOptions

    @Test
    fun noColourDistanceOrShiftIsForgiven() {
        val comparator = options.imageComparator.shouldBeInstanceOf<SimpleImageComparator>()
        comparator.maxDistance shouldBe 0f
        comparator.hShift shouldBe 0
        comparator.vShift shouldBe 0
    }

    @Test
    fun identicalImagesPassAndASinglePixelDifferenceFails() {
        options.resultValidator(ImageComparator.ComparisonResult(0, PIXELS, WIDTH, HEIGHT)) shouldBe true
        options.resultValidator(ImageComparator.ComparisonResult(1, PIXELS, WIDTH, HEIGHT)) shouldBe false
    }

    private companion object {
        const val WIDTH = 720
        const val HEIGHT = 1280
        const val PIXELS = WIDTH * HEIGHT
    }
}
