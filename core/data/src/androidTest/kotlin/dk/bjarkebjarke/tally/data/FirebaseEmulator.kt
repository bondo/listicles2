package dk.bjarkebjarke.tally.data

import android.content.Context
import androidx.test.platform.app.InstrumentationRegistry
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URL

/**
 * The Firebase emulators of the `ui` job (`firebase emulators:exec --only auth,firestore`, project `demo-tally`) on the
 * host, which an Android emulator reaches as 10.0.2.2. No Google Services plugin: tests build their own [FirebaseApp].
 */
object FirebaseEmulator {
    const val HOST = "10.0.2.2"
    const val AUTH_PORT = 9099
    const val FIRESTORE_PORT = 8080
    const val PROJECT_ID = "demo-tally"

    private const val APP_NAME = "emulators"
    private const val CONNECT_TIMEOUT_MS = 2_000
    private const val RULES_FILE = "firestore.rules"
    private const val ALLOW_ALL_RULES =
        "rules_version = '2'; service cloud.firestore { match /databases/{db}/documents " +
            "{ match /{doc=**} { allow read, write: if true; } } }"

    /** Fails the test, naming the service, when nothing listens at [host]:[port]: the emulators are not running. */
    fun requireReachable(
        host: String,
        port: Int,
        service: String,
    ) {
        try {
            Socket().use { it.connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS) }
        } catch (e: IOException) {
            throw AssertionError(
                "The $service emulator is not reachable at $host:$port. Run the tests in `firebase emulators:exec`.",
                e,
            )
        }
    }

    fun requireRunning() {
        requireReachable(HOST, AUTH_PORT, "Auth")
        requireReachable(HOST, FIRESTORE_PORT, "Firestore")
    }

    /**
     * The one [FirebaseApp] of the test process, pointed at both emulators. Shared and never deleted: Firebase Auth
     * keeps the first app it saw in a static, so an app deleted after one test breaks Auth in every later test.
     */
    @Synchronized
    fun app(context: Context): FirebaseApp {
        val existing = FirebaseApp.getApps(context).firstOrNull { it.name == APP_NAME }
        if (existing != null) return existing
        val app =
            FirebaseApp.initializeApp(
                context,
                FirebaseOptions
                    .Builder()
                    .setProjectId(PROJECT_ID)
                    .setApplicationId("1:1:android:0")
                    .setApiKey("fake-api-key")
                    .build(),
                APP_NAME,
            )
        FirebaseAuth.getInstance(app).useEmulator(HOST, AUTH_PORT)
        FirebaseFirestore.getInstance(app).useEmulator(HOST, FIRESTORE_PORT)
        return app
    }

    /** Replaces the Firestore emulator's rules with allow-all ones, for a test of the plumbing and not of the rules. */
    fun loadAllowAllRules() = putRules(ALLOW_ALL_RULES)

    /** Puts back the project's own rules (`firebase/firestore.rules`, synced into the test APK's assets). */
    fun restoreProjectRules() {
        val assets = InstrumentationRegistry.getInstrumentation().context.assets
        putRules(assets.open(RULES_FILE).bufferedReader().use { it.readText() })
    }

    private fun putRules(rules: String) {
        val body =
            org.json.JSONObject().put(
                "rules",
                org.json.JSONObject().put("files", org.json.JSONArray().put(file(rules))),
            )
        val url = URL("http://$HOST:$FIRESTORE_PORT/emulator/v1/projects/$PROJECT_ID:securityRules")
        val connection = url.openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "PUT"
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.outputStream.use { it.write(body.toString().toByteArray()) }
            check(
                connection.responseCode == HttpURLConnection.HTTP_OK,
            ) { "Loading rules failed: HTTP ${connection.responseCode}" }
        } finally {
            connection.disconnect()
        }
    }

    private fun file(rules: String) =
        org.json
            .JSONObject()
            .put("name", RULES_FILE)
            .put("content", rules)
}
