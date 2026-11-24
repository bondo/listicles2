package dk.bjarkebjarke.tally.start

import android.app.Activity
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.lifecycle.Lifecycle
import dagger.hilt.android.testing.BindValue
import dagger.hilt.android.testing.HiltAndroidRule
import dagger.hilt.android.testing.HiltAndroidTest
import dagger.hilt.android.testing.HiltTestApplication
import dagger.hilt.android.testing.UninstallModules
import dk.bjarkebjarke.tally.ApplicationScope
import dk.bjarkebjarke.tally.MainActivity
import dk.bjarkebjarke.tally.R
import dk.bjarkebjarke.tally.domain.session.LocalUserData
import dk.bjarkebjarke.tally.domain.session.SessionState
import dk.bjarkebjarke.tally.session.SessionModule
import dk.bjarkebjarke.tally.session.StartedActivity
import dk.bjarkebjarke.tally.testing.FakeLocalUserData
import dk.bjarkebjarke.tally.testing.FakeSessionState
import io.kotest.matchers.shouldBe
import io.kotest.matchers.types.shouldBeSameInstanceAs
import io.kotest.matchers.types.shouldNotBeSameInstanceAs
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.job
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.util.Collections
import javax.inject.Inject

/**
 * M1-60: the real activity, its Hilt ViewModel and the root, with a signed-out session, open on sign-in. The fake
 * session and local copy replace the whole Firebase session module (M1-88, M1-89), so the test needs no Firebase app.
 */
@HiltAndroidTest
@UninstallModules(SessionModule::class)
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

    /** What the signed-out cleanup (M1-89) deletes; it runs on a thread of the application scope. */
    private val steps: MutableList<String> = Collections.synchronizedList(mutableListOf())

    @BindValue
    @JvmField
    val userData: LocalUserData = FakeLocalUserData(steps = steps)

    @Inject
    lateinit var startedActivity: StartedActivity

    @Inject
    @ApplicationScope
    lateinit var applicationScope: CoroutineScope

    @Test
    fun signedOutStartShowsSignIn() {
        // The update gate reads its remembered minimum on IO (R1-02), so the first state arrives a moment later.
        compose.waitUntil(START_TIMEOUT_MS) {
            compose.onAllNodesWithText(compose.activity.getString(R.string.app_tag)).fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText(compose.activity.getString(R.string.app_tag)).assertExists()
        compose.onNodeWithText(compose.activity.getString(R.string.lists_empty_title)).assertDoesNotExist()
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

    /**
     * M1-89: MainActivity starts the process's one signed-out cleanup, so a signed-out start deletes a copy that a
     * session left on the phone. A recreated MainActivity starts no second watcher.
     */
    @Test
    fun theStartedActivityStartsTheOneSignedOutCleanup() {
        hilt.inject()
        compose.waitUntil(START_TIMEOUT_MS) { "cleared" in steps }
        steps shouldBe listOf("clear", "cleared")
        val scope = applicationScope.coroutineContext.job
        val watchers = scope.children.count()

        compose.activityRule.scenario.recreate()

        scope.children.count() shouldBe watchers
        steps shouldBe listOf("clear", "cleared")
    }

    private companion object {
        const val START_TIMEOUT_MS = 5_000L
    }
}
