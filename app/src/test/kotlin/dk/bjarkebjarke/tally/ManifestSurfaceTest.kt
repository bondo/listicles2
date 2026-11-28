package dk.bjarkebjarke.tally

import io.kotest.matchers.collections.shouldContainExactlyInAnyOrder
import io.kotest.matchers.collections.shouldNotContainAnyOf
import io.kotest.matchers.shouldBe
import org.junit.jupiter.api.Test
import org.w3c.dom.Element
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory

/**
 * PR 368 R1-01, S1-03 (checklist section 9: the fewest permissions, no component exported unless needed): the merged
 * release manifest, the one that ships, asks for exactly these permissions and exports exactly these components, each
 * with its reason. A dependency that brings another one fails here until a manifest removes it (core/data's, for the
 * libraries that module brings) or this test takes it with a reason. Release unit tests are off, so Gradle hands this
 * test the release manifest.
 */
class ManifestSurfaceTest {
    private val manifest: Element =
        DocumentBuilderFactory
            .newInstance()
            .apply { isNamespaceAware = true }
            .newDocumentBuilder()
            .parse(File(checkNotNull(System.getProperty(PROPERTY)) { "$PROPERTY is not set" }))
            .documentElement

    private fun elements(vararg tags: String): List<Element> =
        tags.flatMap { tag ->
            val nodes = manifest.getElementsByTagName(tag)
            List(nodes.length) { nodes.item(it) as Element }
        }

    private fun Element.android(attribute: String): String = getAttributeNS(ANDROID, attribute)

    private fun requestedPermissions() =
        elements("uses-permission", "uses-permission-sdk-23").map { it.android("name") }

    /** Each exported component with the permission a caller needs, "" for none. */
    private fun exportedComponents() =
        elements("activity", "activity-alias", "service", "receiver", "provider")
            .filter { it.android("exported") == "true" }
            .associate { it.android("name") to it.android("permission") }

    @Test
    fun asksForExactlyThePermissionsTallyUses() {
        requestedPermissions() shouldContainExactlyInAnyOrder
            listOf(
                // M1-30: AndroidConnectivity reads the active network (SYNC-03).
                "android.permission.ACCESS_NETWORK_STATE",
                // M1-66: Firebase Auth and Firestore talk to Firebase.
                "android.permission.INTERNET",
                // androidx.core: ContextCompat keeps a dynamically registered receiver private before Android 13.
                "dk.bjarkebjarke.tally.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION",
                // firebase-auth's reCAPTCHA SDK reads it once the Firebase project turns on reCAPTCHA protection
                // for email and password sign-in (off now): a console switch, so the shipped app must carry it.
                "com.google.android.providers.gsf.permission.READ_GSERVICES",
            )
    }

    @Test
    fun asksForNoBiometricPermission() {
        // androidx.biometric comes with androidx.credentials for credential provider apps, which Tally is not.
        requestedPermissions() shouldNotContainAnyOf
            listOf("android.permission.USE_BIOMETRIC", "android.permission.USE_FINGERPRINT")
    }

    @Test
    fun exportsExactlyTheLauncherAndComponentsOnlyTheSystemCanReach() {
        exportedComponents() shouldBe
            mapOf(
                "dk.bjarkebjarke.tally.MainActivity" to "",
                // androidx.profileinstaller: only the shell may ask it to install or save the baseline profile.
                "androidx.profileinstaller.ProfileInstallReceiver" to "android.permission.DUMP",
                // play-services-auth, for legacy GoogleSignIn, which no Tally flow uses: it never starts here. It stays
                // because only Google Play services gets in (this permission and a caller check), and a removal entry
                // needs a lint suppression (MissingClass: play-services-auth is on no module's compile classpath).
                "com.google.android.gms.auth.api.signin.RevocationBoundService" to
                    "com.google.android.gms.auth.api.signin.permission.REVOCATION_NOTIFICATION",
            )
    }

    /** M1-25 (privacy Q3): Crashlytics collects nothing until the user turns "Send crash reports" on. */
    @Test
    fun crashlyticsCollectionIsOffInTheManifest() {
        val flag = elements("meta-data").single { it.android("name") == "firebase_crashlytics_collection_enabled" }
        flag.android("value") shouldBe "false"
    }

    @Test
    fun hasNoBrowserEntryPointForFirebaseAuth() {
        // Browser sign-in with an OAuthProvider, and phone number verification: Tally has neither.
        elements("activity").map { it.android("name") } shouldNotContainAnyOf
            listOf(
                "com.google.firebase.auth.internal.GenericIdpActivity",
                "com.google.firebase.auth.internal.RecaptchaActivity",
            )
    }

    private companion object {
        const val ANDROID = "http://schemas.android.com/apk/res/android"
        const val PROPERTY = "tally.releaseManifest"
    }
}
