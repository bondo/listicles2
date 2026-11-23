package dk.bjarkebjarke.tally

import dagger.hilt.android.testing.HiltAndroidRule
import dagger.hilt.android.testing.HiltAndroidTest
import dagger.hilt.android.testing.HiltTestApplication
import dagger.hilt.internal.GeneratedComponentManager
import dagger.hilt.internal.GeneratedComponentManagerHolder
import dk.bjarkebjarke.tally.connectivity.AndroidConnectivity
import dk.bjarkebjarke.tally.domain.connectivity.Connectivity
import dk.bjarkebjarke.tally.domain.session.SessionState
import dk.bjarkebjarke.tally.domain.start.EmailVerification
import dk.bjarkebjarke.tally.domain.start.HouseholdNotices
import dk.bjarkebjarke.tally.domain.start.NameState
import dk.bjarkebjarke.tally.domain.start.UpdateGate
import io.kotest.matchers.booleans.shouldBeTrue
import io.kotest.matchers.shouldBe
import io.kotest.matchers.types.shouldBeInstanceOf
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
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

    @Inject
    lateinit var session: SessionState

    @Inject
    lateinit var update: UpdateGate

    @Inject
    lateinit var email: EmailVerification

    @Inject
    lateinit var name: NameState

    @Inject
    lateinit var notices: HouseholdNotices

    /** M1-62: until the gate tasks bind real sources, every gate passes (M1-27, M1-15, M1-39, M1-18). */
    @Test
    fun gateStandInsAllPass() {
        hilt.inject()
        runBlocking {
            update.updateRequired().first() shouldBe false
            email.verified().first() shouldBe true
            name.saved().first() shouldBe true
            notices.pending().first() shouldBe null
        }
    }

    @Test
    fun connectivityIsTheAndroidImplementation() {
        hilt.inject()
        connectivity.shouldBeInstanceOf<AndroidConnectivity>()
    }

    /** M1-60: until M1-14 binds the Firebase Auth session, nobody is signed in, so the app opens on sign-in. */
    @Test
    fun sessionIsSignedOutUntilAuthExists() {
        hilt.inject()
        runBlocking { session.signedIn().first() } shouldBe false
    }
}

/** Without the test application: the manifest's application and MainActivity are the app's own Hilt entry points. */
@RunWith(RobolectricTestRunner::class)
class TallyApplicationTest {
    @Test
    fun manifestApplicationAndMainActivityAreHiltEntryPoints() {
        val app = RuntimeEnvironment.getApplication()
        app.shouldBeInstanceOf<TallyApplication>()
        app.shouldBeInstanceOf<GeneratedComponentManager<*>>()
        GeneratedComponentManagerHolder::class.java.isAssignableFrom(MainActivity::class.java).shouldBeTrue()
    }
}
