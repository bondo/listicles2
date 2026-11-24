package dk.bjarkebjarke.tally.session

import android.app.Application
import androidx.activity.ComponentActivity
import io.kotest.matchers.shouldBe
import io.kotest.matchers.types.shouldBeSameInstanceAs
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** M1-88: Credential Manager opens Google's account picker in the app's started activity, never in a stopped one. */
@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class)
class StartedActivityTest {
    private val started = StartedActivity()

    /** An activity that adds [started] to its own lifecycle, as MainActivity does. */
    private fun observed() =
        Robolectric.buildActivity(ComponentActivity::class.java).also {
            it.get().lifecycle.addObserver(started)
        }

    @Test
    fun theActivityIsCurrentFromItsStartToItsStop() {
        val activity = observed()

        activity.create()
        started.current() shouldBe null
        activity.start()
        started.current() shouldBeSameInstanceAs activity.get()
        activity.resume().pause()
        started.current() shouldBeSameInstanceAs activity.get()
        activity.stop()
        started.current() shouldBe null
    }

    /** A second MainActivity (a new task, say) starts before the first one stops: only its own stop clears it. */
    @Test
    fun anActivityThatStopsLaterDoesNotClearTheOneStartedAfterIt() {
        val first = observed().setup()
        val second = observed()

        first.pause()
        second.setup()
        first.stop()
        started.current() shouldBeSameInstanceAs second.get()

        second.pause().stop()
        started.current() shouldBe null
    }
}
