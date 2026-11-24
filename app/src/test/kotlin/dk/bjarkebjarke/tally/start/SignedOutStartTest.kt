package dk.bjarkebjarke.tally.start

import android.app.Activity
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.lifecycle.Lifecycle
import dagger.hilt.android.testing.BindValue
import dagger.hilt.android.testing.HiltAndroidRule
import dagger.hilt.android.testing.HiltAndroidTest
import dagger.hilt.android.testing.HiltTestApplication
import dagger.hilt.android.testing.UninstallModules
import dk.bjarkebjarke.tally.MainActivity
import dk.bjarkebjarke.tally.R
import dk.bjarkebjarke.tally.connectivity.ConnectivityModule
import dk.bjarkebjarke.tally.domain.connectivity.Connectivity
import dk.bjarkebjarke.tally.domain.session.Authentication
import dk.bjarkebjarke.tally.domain.session.GoogleCredentials
import dk.bjarkebjarke.tally.domain.session.SessionState
import dk.bjarkebjarke.tally.session.SessionModule
import dk.bjarkebjarke.tally.session.StartedActivity
import dk.bjarkebjarke.tally.testing.FakeAuthentication
import dk.bjarkebjarke.tally.testing.FakeConnectivity
import dk.bjarkebjarke.tally.testing.FakeGoogleCredentials
import dk.bjarkebjarke.tally.testing.FakeSessionState
import io.kotest.matchers.shouldBe
import io.kotest.matchers.types.shouldBeSameInstanceAs
import io.kotest.matchers.types.shouldNotBeSameInstanceAs
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import javax.inject.Inject

/**
 * M1-60: the real activity, its Hilt ViewModel and the root, with a signed-out session, open on sign-in. The fake
 * session replaces the whole Firebase session module (M1-88), so the test needs no Firebase app.
 */
@HiltAndroidTest
@UninstallModules(SessionModule::class, ConnectivityModule::class)
@RunWith(RobolectricTestRunner::class)
@Config(application = HiltTestApplication::class)
class SignedOutStartTest {
    @get:Rule(order = 0)
    val hilt = HiltAndroidRule(this)

    @get:Rule(order = 1)
    val compose = createAndroidComposeRule<MainActivity>()

    @BindValue
    @JvmField
    val session: SessionState = FakeSessionState(signedIn = false)

    @BindValue
    @JvmField
    val connectivity: Connectivity = FakeConnectivity(online = true)

    @BindValue
    @JvmField
    val credentials: GoogleCredentials = FakeGoogleCredentials()

    private val fakeAuthentication = FakeAuthentication()

    @BindValue
    @JvmField
    val authentication: Authentication = fakeAuthentication

    @Inject
    lateinit var startedActivity: StartedActivity

    @Test
    fun signedOutStartShowsSignIn() {
        // The update gate reads its remembered minimum on IO (R1-02), so the first state arrives a moment later.
        compose.waitUntil(START_TIMEOUT_MS) {
            compose.onAllNodesWithText(compose.activity.getString(R.string.app_tag)).fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText(compose.activity.getString(R.string.app_tag)).assertExists()
        compose.onNodeWithText(compose.activity.getString(R.string.lists_empty_title)).assertDoesNotExist()
    }

    /** M1-16: the sign-in screen's Google button reaches the graph's GoogleSignIn (fake picker and Firebase). */
    @Test
    fun theGoogleButtonSignsInThroughTheGraph() {
        val google = compose.activity.getString(R.string.signin_google)
        compose.waitUntil(START_TIMEOUT_MS) { compose.onAllNodesWithText(google).fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText(google).performClick()
        compose.waitUntil(START_TIMEOUT_MS) { fakeAuthentication.googleIdTokens.isNotEmpty() }
        fakeAuthentication.googleIdTokens shouldBe listOf("fake-google-id-token")
    }

    /**
     * M1-88: Google's account picker (from sign-in) opens in MainActivity while it is started, because MainActivity
     * adds the app's one [StartedActivity] to its own lifecycle. Its stop clears it, and a recreated MainActivity (a
     * rotation, say) is the one the picker opens in next.
     */
    @Test
    fun theAccountPickerOpensInTheStartedMainActivity() {
        hilt.inject()
        val scenario = compose.activityRule.scenario
        val first = compose.activity
        startedActivity.current() shouldBeSameInstanceAs first

        scenario.moveToState(Lifecycle.State.CREATED)
        startedActivity.current() shouldBe null
        scenario.moveToState(Lifecycle.State.RESUMED)
        startedActivity.current() shouldBeSameInstanceAs first

        scenario.recreate()
        compose.activity shouldNotBeSameInstanceAs first
        startedActivity.current() shouldBeSameInstanceAs compose.activity
    }

    /**
     * M1-88: the picker's own translucent activity opens above MainActivity, which only pauses, and closes again.
     * Application-wide activity callbacks would see that activity too: its stop would clear MainActivity while it stays
     * started, and the next sign-in would find no activity.
     */
    @Test
    fun thePickersOwnActivityAboveMainActivityChangesNothing() {
        hilt.inject()
        val scenario = compose.activityRule.scenario
        val main = compose.activity
        val picker = Robolectric.buildActivity(Activity::class.java)

        scenario.moveToState(Lifecycle.State.STARTED)
        picker.setup()
        startedActivity.current() shouldBeSameInstanceAs main
        picker.pause()
        scenario.moveToState(Lifecycle.State.RESUMED)
        picker.stop().destroy()

        startedActivity.current() shouldBeSameInstanceAs main
    }

    private companion object {
        const val START_TIMEOUT_MS = 5_000L
    }
}
