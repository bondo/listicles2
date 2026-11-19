package dev.listicles.app

import android.os.Build
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * Issue 213: Robolectric must boot its Android sandbox while the test JVM blocks the network (core/testing).
 * It needs the android-all jar for the SDK level, which it downloads at test runtime unless it is told where
 * the jar is. A JUnit 4 test, so it runs only through the vintage engine.
 */
@RunWith(RobolectricTestRunner::class)
class RobolectricUnderNetworkBlockTest {
    @Test
    fun sandboxBootsWithoutNetwork() {
        assertEquals(35, Build.VERSION.SDK_INT)
    }
}
