package dk.bjarkebjarke.tally

import dk.bjarkebjarke.tally.data.session.CredentialManagerGoogleCredentials
import io.kotest.matchers.shouldBe
import io.kotest.matchers.shouldNotBe
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment

/** M1-30: without the real google-services.json the build carries the demo-tally stand-in; Gradle says which case. */
@RunWith(RobolectricTestRunner::class)
class GoogleServicesConfigTest {
    private fun resource(name: String): String {
        val app = RuntimeEnvironment.getApplication()
        val id = app.resources.getIdentifier(name, "string", app.packageName)
        id shouldNotBe 0
        return app.getString(id)
    }

    @Test
    fun theBuildCarriesTheStandInExactlyWhenNoRealConfigIsPresent() {
        val standIn = System.getProperty("tally.googleServicesStandIn")
        standIn shouldNotBe null
        if (standIn.toBoolean()) {
            resource("project_id") shouldBe "demo-tally"
            resource("google_app_id") shouldBe "1:000000000000:android:0000000000000000"
            resource("google_api_key") shouldBe "stand-in-not-a-key"
            // M1-66: the plugin's value from the stand-in's web client overrides :core:data's empty default.
            resource("default_web_client_id") shouldBe STAND_IN_WEB_CLIENT
            CredentialManagerGoogleCredentials.webClientId(RuntimeEnvironment.getApplication()) shouldBe
                STAND_IN_WEB_CLIENT
        } else {
            resource("project_id") shouldNotBe "demo-tally"
        }
    }

    private companion object {
        const val STAND_IN_WEB_CLIENT = "000000000000-stand-in.apps.googleusercontent.com"
    }
}
