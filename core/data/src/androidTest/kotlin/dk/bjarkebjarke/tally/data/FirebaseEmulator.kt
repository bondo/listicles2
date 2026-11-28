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
    private const val API_KEY = "fake-api-key"

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
                    .setApiKey(API_KEY)
                    .build(),
                APP_NAME,
            )
        FirebaseAuth.getInstance(app).useEmulator(HOST, AUTH_PORT)
        firestore(app)
        return app
    }

    private var configuredFirestore: FirebaseFirestore? = null

    /**
     * The app's Firestore, pointed at the emulator. A sign-out terminates the instance (M1-14 step 2) and `getInstance`
     * then makes a new one, so each new instance is pointed at the emulator here before anything uses it.
     */
    @Synchronized
    fun firestore(app: FirebaseApp): FirebaseFirestore {
        val instance = FirebaseFirestore.getInstance(app)
        if (instance !== configuredFirestore) {
            instance.useEmulator(HOST, FIRESTORE_PORT)
            configuredFirestore = instance
        }
        return instance
    }

    /** Replaces the Firestore emulator's rules with allow-all ones, for a test of the plumbing and not of the rules. */
    fun loadAllowAllRules() = putRules(ALLOW_ALL_RULES)

    /** Puts back the project's own rules (`firebase/firestore.rules`, synced into the test APK's assets). */
    fun restoreProjectRules() {
        val assets = InstrumentationRegistry.getInstrumentation().context.assets
        putRules(assets.open(RULES_FILE).bufferedReader().use { it.readText() })
    }

    /**
     * Disables [uid]'s account, as an administrator would (the Auth emulator takes the token `owner` as admin access).
     * The session on the phone lasts until Firebase next refreshes its token, which the emulator then refuses
     * (`USER_DISABLED`).
     */
    fun disableUser(uid: String) =
        send(
            "POST",
            URL("http://$HOST:$AUTH_PORT/identitytoolkit.googleapis.com/v1/projects/$PROJECT_ID/accounts:update"),
            JSONObject().put("localId", uid).put("disableUser", true),
            "Disabling the user",
            authorization = "Bearer owner",
        )

    /** Turns email enumeration protection on (as in the real project, M1-O1, M1.md R1) or off (the default). */
    fun emailPrivacy(on: Boolean) {
        val url = URL("http://$HOST:$AUTH_PORT/emulator/v1/projects/$PROJECT_ID/config")
        val privacy = JSONObject().put("enableImprovedEmailPrivacy", on)
        send("PATCH", url, JSONObject().put("emailPrivacyConfig", privacy), "Setting email privacy")
    }

    /** The codes of the emails the Auth emulator "sent" to [email] (`VERIFY_EMAIL`, `PASSWORD_RESET`), oldest first. */
    fun oobCodes(
        email: String,
        requestType: String,
    ): List<String> {
        val url = URL("http://$HOST:$AUTH_PORT/emulator/v1/projects/$PROJECT_ID/oobCodes")
        val codes =
            JSONObject(send("GET", url, null, "Reading the sent emails")).optJSONArray("oobCodes") ?: JSONArray()
        return (0 until codes.length())
            .map { codes.getJSONObject(it) }
            .filter { it.getString("email") == email && it.getString("requestType") == requestType }
            .map { it.getString("oobCode") }
    }

    /** Opens the link of a verification email, as the user does in their mail app. */
    fun openVerificationLink(code: String) {
        send("POST", identityToolkit("accounts:update"), JSONObject().put("oobCode", code), "Verifying the email")
    }

    /** The accounts with [email], as an administrator sees them (`localId`, `providerUserInfo`). */
    fun accounts(email: String): JSONArray {
        val url = URL("http://$HOST:$AUTH_PORT/identitytoolkit.googleapis.com/v1/projects/$PROJECT_ID/accounts:lookup")
        val body = JSONObject().put("email", JSONArray().put(email))
        val answer = JSONObject(send("POST", url, body, "Looking up the account", authorization = "Bearer owner"))
        return answer.optJSONArray("users") ?: JSONArray()
    }

    private fun identityToolkit(method: String) =
        URL("http://$HOST:$AUTH_PORT/identitytoolkit.googleapis.com/v1/$method?key=$API_KEY")

    private fun putRules(rules: String) =
        send(
            "PUT",
            URL("http://$HOST:$FIRESTORE_PORT/emulator/v1/projects/$PROJECT_ID:securityRules"),
            JSONObject().put("rules", JSONObject().put("files", JSONArray().put(file(rules)))),
            "Loading rules",
        )

    /** Answers the response body. */
    private fun send(
        method: String,
        url: URL,
        body: JSONObject?,
        what: String,
        authorization: String? = null,
    ): String {
        val connection = url.openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.setRequestProperty("Content-Type", "application/json")
            authorization?.let { connection.setRequestProperty("Authorization", it) }
            if (body != null) {
                connection.doOutput = true
                connection.outputStream.use { it.write(body.toString().toByteArray()) }
            }
            check(connection.responseCode == HttpURLConnection.HTTP_OK) {
                "$what failed: HTTP ${connection.responseCode}"
            }
            return connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private fun file(rules: String) =
        JSONObject()
            .put("name", RULES_FILE)
            .put("content", rules)
}
