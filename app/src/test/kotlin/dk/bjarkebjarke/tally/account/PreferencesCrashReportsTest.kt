package dk.bjarkebjarke.tally.account

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import io.kotest.matchers.shouldBe
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** M1-25 (privacy Q3): "Send crash reports" is off until switched on, and Crashlytics gets the stored choice. */
@RunWith(RobolectricTestRunner::class)
class PreferencesCrashReportsTest {
    private val context: Context = ApplicationProvider.getApplicationContext()
    private val applied = mutableListOf<Boolean>()

    private fun reports() = PreferencesCrashReports(context) { applied += it }

    @Test
    fun isOffUntilTheUserTurnsItOn() {
        reports().isSending() shouldBe false
    }

    @Test
    fun turningItOnAndOffReachesCrashlyticsAndSurvivesANewInstance() {
        reports().setSending(true)
        reports().isSending() shouldBe true
        reports().setSending(false)
        reports().isSending() shouldBe false
        applied shouldBe listOf(true, false)
    }

    @Test
    fun startingAppliesTheStoredChoiceEvenWhenOff() {
        reports().applyStored()
        reports().setSending(true)
        applied.clear()
        reports().applyStored()
        applied shouldBe listOf(true)
    }
}
