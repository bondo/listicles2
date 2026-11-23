package dk.bjarkebjarke.tally.appcheck

import com.google.firebase.appcheck.AppCheckProviderFactory
import com.google.firebase.appcheck.debug.DebugAppCheckProviderFactory
import dagger.hilt.android.testing.HiltAndroidRule
import dagger.hilt.android.testing.HiltAndroidTest
import dagger.hilt.android.testing.HiltTestApplication
import io.kotest.matchers.types.shouldBeInstanceOf
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import javax.inject.Inject

/**
 * M1-26 (R5): the debug build's graph provides the debug App Check provider, which needs no Play Integrity. The release
 * graph provides the Play Integrity one (a release-source-set module; unit tests run the debug variant only).
 * Enforcement stays off in the console (M1-O4), so neither provider changes what the app can reach today.
 */
@HiltAndroidTest
@RunWith(RobolectricTestRunner::class)
@Config(application = HiltTestApplication::class)
class AppCheckModuleTest {
    @get:Rule
    val hilt = HiltAndroidRule(this)

    @Inject
    lateinit var factory: AppCheckProviderFactory

    @Test
    fun debugBuildInstallsTheDebugFactory() {
        hilt.inject()
        factory.shouldBeInstanceOf<DebugAppCheckProviderFactory>()
    }
}
