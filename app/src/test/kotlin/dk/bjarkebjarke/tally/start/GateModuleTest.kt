package dk.bjarkebjarke.tally.start

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import dk.bjarkebjarke.tally.testing.FakeMinVersionRemote
import dk.bjarkebjarke.tally.testing.FakeMinVersionStore
import io.kotest.matchers.shouldBe
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** R1-04: the real update gate compares the minimum with this build's version code (app/build.gradle.kts). */
@RunWith(RobolectricTestRunner::class)
class GateModuleTest {
    private val context: Context = ApplicationProvider.getApplicationContext()

    private fun required(min: Long?) =
        runBlocking {
            GateModule.updateGate(context, FakeMinVersionRemote(min), FakeMinVersionStore()).updateRequired().first()
        }

    @Test
    fun aMinimumAboveTheInstalledVersionRequiresAnUpdate() {
        required(INSTALLED + 1) shouldBe true
        required(Long.MAX_VALUE) shouldBe true
    }

    @Test
    fun theInstalledVersionAndBelowDoNotRequireOne() {
        required(INSTALLED) shouldBe false
        required(INSTALLED - 1) shouldBe false
        required(0L) shouldBe false
        required(null) shouldBe false
    }

    private companion object {
        const val INSTALLED = 1L
    }
}
