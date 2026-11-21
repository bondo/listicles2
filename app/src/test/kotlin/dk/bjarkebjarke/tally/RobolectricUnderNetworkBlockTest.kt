package dk.bjarkebjarke.tally

import android.os.Build
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
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
        assertTrue(Build.VERSION.SDK_INT >= MIN_SDK)
    }

    /** Screenshot and UI tests must run against the Android version the app targets (R1-02), not an older one. */
    @Test
    fun sandboxRunsTheTargetSdk() {
        assertEquals(requireNotNull(System.getProperty("tally.targetSdk")).toInt(), Build.VERSION.SDK_INT)
    }

    private companion object {
        const val MIN_SDK = 26 // minSdk of the app
    }
}
