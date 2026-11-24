package dk.bjarkebjarke.tally.data.session

import android.app.Activity
import android.content.Context
import androidx.credentials.ClearCredentialStateRequest
import androidx.credentials.CredentialManager
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.ClearCredentialException
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import androidx.credentials.exceptions.NoCredentialException
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.android.libraries.identity.googleid.GoogleIdTokenParsingException
import dk.bjarkebjarke.tally.data.R
import dk.bjarkebjarke.tally.domain.session.GoogleCredentials
import dk.bjarkebjarke.tally.domain.session.GoogleIdToken

/**
 * Credential Manager with the Google ID option (Sign in with Google; checklist section 9). The account picker opens in
 * the [foreground] activity: Credential Manager asks for an activity context, so its UI starts in the app's task. It
 * offers first the accounts that signed in to the app before, one picked without asking (auto-select, until a sign-out
 * clears the credential state); with none of those ([NoCredentialException]) every Google account on the phone.
 * [webClientId] is the Firebase project's web client id (the companion's `webClientId` reads it); empty means Google
 * sign-in is not set up in Firebase, and then nothing is asked.
 */
class CredentialManagerGoogleCredentials(
    private val credentialManager: CredentialManager,
    private val foreground: ForegroundActivity,
    private val webClientId: String,
) : GoogleCredentials {
    override suspend fun idToken(): GoogleIdToken {
        val activity = foreground.current()
        if (activity == null || webClientId.isEmpty()) return GoogleIdToken.Failed
        return try {
            try {
                pick(activity, authorizedAccountsOnly = true)
            } catch (expected: NoCredentialException) {
                pick(activity, authorizedAccountsOnly = false)
            }
        } catch (expected: NoCredentialException) {
            GoogleIdToken.NoAccount
        } catch (expected: GetCredentialCancellationException) {
            GoogleIdToken.Cancelled
        } catch (expected: GetCredentialException) {
            // No credential provider on the phone, a provider error or an interrupted request.
            GoogleIdToken.Failed
        }
    }

    private suspend fun pick(
        activity: Activity,
        authorizedAccountsOnly: Boolean,
    ): GoogleIdToken {
        val option =
            GetGoogleIdOption
                .Builder()
                .setServerClientId(webClientId)
                .setFilterByAuthorizedAccounts(authorizedAccountsOnly)
                .setAutoSelectEnabled(authorizedAccountsOnly)
                .build()
        val credential = credentialManager.getCredential(activity, GetCredentialRequest(listOf(option))).credential
        if (credential.type != GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) return GoogleIdToken.Failed
        return try {
            GoogleIdToken.Picked(GoogleIdTokenCredential.createFrom(credential.data).idToken)
        } catch (expected: GoogleIdTokenParsingException) {
            GoogleIdToken.Failed
        }
    }

    override suspend fun clearCredentialState() {
        try {
            credentialManager.clearCredentialState(ClearCredentialStateRequest())
        } catch (expected: ClearCredentialException) {
            // No provider, or nothing to clear: the next sign-in shows the picker either way.
        }
    }

    companion object {
        /**
         * The web client id from google-services.json: the Google Services plugin generates the app's own
         * `default_web_client_id`, which overrides this module's empty default. Empty while Firebase has no web client
         * (Google sign-in not enabled there).
         */
        fun webClientId(context: Context): String = context.getString(R.string.default_web_client_id)
    }
}

/** The activity the user sees, if any: Credential Manager shows the account picker in it (M1-66). */
fun interface ForegroundActivity {
    fun current(): Activity?
}
