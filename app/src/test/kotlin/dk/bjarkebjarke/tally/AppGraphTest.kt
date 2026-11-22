package dk.bjarkebjarke.tally

import dagger.hilt.android.testing.HiltAndroidRule
import dagger.hilt.android.testing.HiltAndroidTest
import dagger.hilt.android.testing.HiltTestApplication
import dagger.hilt.internal.GeneratedComponentManager
import dagger.hilt.internal.GeneratedComponentManagerHolder
import dk.bjarkebjarke.tally.connectivity.AndroidConnectivity
import dk.bjarkebjarke.tally.domain.connectivity.Connectivity
import io.kotest.matchers.booleans.shouldBeTrue
import io.kotest.matchers.types.shouldBeInstanceOf
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import javax.inject.Inject

/** M1-30: the app is a Hilt app, its activity is an entry point, and the graph binds the app's own implementations. */
@HiltAndroidTest
@RunWith(RobolectricTestRunner::class)
@Config(application = HiltTestApplication::class)
class AppGraphTest {
    @get:Rule
    val hilt = HiltAndroidRule(this)

    @Inject
    lateinit var connectivity: Connectivity

    @Test
    fun connectivityIsTheAndroidImplementation() {
        hilt.inject()
        connectivity.shouldBeInstanceOf<AndroidConnectivity>()
    }

    @Test
    fun mainActivityIsAHiltEntryPoint() {
        GeneratedComponentManagerHolder::class.java.isAssignableFrom(MainActivity::class.java).shouldBeTrue()
    }
}

/** Without the test application: the manifest's application is the app's own Hilt application. */
@RunWith(RobolectricTestRunner::class)
class TallyApplicationTest {
    @Test
    fun manifestApplicationIsTheHiltApplication() {
        val app = RuntimeEnvironment.getApplication()
        app.shouldBeInstanceOf<TallyApplication>()
        app.shouldBeInstanceOf<GeneratedComponentManager<*>>()
    }
}
