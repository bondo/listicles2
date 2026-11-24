package dk.bjarkebjarke.tally.session

import android.app.Activity
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

    /**
     * The picker's own translucent activity opens above MainActivity, which only pauses, and closes again. Application
     * wide activity callbacks would see it: its stop would clear the activity while MainActivity stays started, and the
     * next sign-in would find none.
     */
    @Test
    fun thePickersActivityAboveItChangesNothing() {
        val main = observed().setup()
        val picker = Robolectric.buildActivity(Activity::class.java)

        main.pause()
        picker.setup()
        started.current() shouldBeSameInstanceAs main.get()
        picker.pause()
        main.resume()
        picker.stop().destroy()

        started.current() shouldBeSameInstanceAs main.get()
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
