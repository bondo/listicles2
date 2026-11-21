package dk.bjarkebjarke.tally

import io.kotest.matchers.shouldBe
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * M1-29: the app is Tally. The application id (permanent once published) and the namespace are
 * `dk.bjarkebjarke.tally`, and the launcher label is "Tally" in English and Danish.
 */
@RunWith(RobolectricTestRunner::class)
class RenameTest {
    private val expectedPackage = "dk.bjarkebjarke.tally"

    private fun appName(): String {
        val app = RuntimeEnvironment.getApplication()
        val id = app.resources.getIdentifier("app_name", "string", app.packageName)
        return app.getString(id)
    }

    @Test
    fun applicationIdIsTally() {
        RuntimeEnvironment.getApplication().packageName shouldBe expectedPackage
    }

    @Test
    fun namespaceHoldsTheLauncherActivity() {
        Class.forName("$expectedPackage.MainActivity").simpleName shouldBe "MainActivity"
    }

    @Test
    fun englishLabelIsTally() {
        appName() shouldBe "Tally"
    }

    @Test
    @Config(qualifiers = "da")
    fun danishLabelIsTally() {
        appName() shouldBe "Tally"
    }
}
