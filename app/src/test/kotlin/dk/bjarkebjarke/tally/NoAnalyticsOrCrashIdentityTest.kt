package dk.bjarkebjarke.tally

import io.kotest.matchers.collections.shouldBeEmpty
import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test
import java.io.File

/** M1-25 (privacy Q3, Q13): no Analytics on the classpath, and Crashlytics never gets a user id or custom keys. */
class NoAnalyticsOrCrashIdentityTest {
    @Test
    fun firebaseAnalyticsIsNotOnTheRuntimeClasspath() {
        val found = ANALYTICS_CLASSES.filter { runCatching { Class.forName(it) }.isSuccess }
        found.shouldBeEmpty()
    }

    @Test
    fun theClasspathCheckCanFail() {
        // Negative case: a class that is on the classpath is found by the same lookup.
        runCatching { Class.forName("com.google.firebase.crashlytics.FirebaseCrashlytics") }.isSuccess shouldBe true
    }

    @Test
    fun noSourceSetsAUserIdOrCustomKeys() {
        val sources = File("src/main").walkTopDown().filter { it.extension == "kt" }.toList()
        (sources.size > 0) shouldBe true
        sources.filter { file -> IDENTITY_CALLS.any { it.containsMatchIn(file.readText()) } }.shouldBeEmpty()
    }

    @Test
    fun theIdentityCheckCanFail() {
        IDENTITY_CALLS.any { it.containsMatchIn("crashlytics.setUserId(uid)") } shouldBe true
        IDENTITY_CALLS.any { it.containsMatchIn("crashlytics.setCustomKey(\"a\", 1)") } shouldBe true
    }

    private companion object {
        val ANALYTICS_CLASSES =
            listOf(
                "com.google.firebase.analytics.FirebaseAnalytics",
                "com.google.android.gms.measurement.AppMeasurement",
            )
        val IDENTITY_CALLS = listOf(Regex("""\bsetUserId\b"""), Regex("""\bsetCustomKeys?\b"""))
    }
}
