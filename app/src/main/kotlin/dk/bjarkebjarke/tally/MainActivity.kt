package dk.bjarkebjarke.tally

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.lifecycle.lifecycleScope
import dagger.hilt.android.AndroidEntryPoint
import dk.bjarkebjarke.tally.account.AccountRoute
import dk.bjarkebjarke.tally.account.AccountViewModel
import dk.bjarkebjarke.tally.account.initialOf
import dk.bjarkebjarke.tally.domain.account.AccountProfiles
import dk.bjarkebjarke.tally.domain.session.SignedOutCleanup
import dk.bjarkebjarke.tally.session.StartedActivity
import dk.bjarkebjarke.tally.signin.SignInRoute
import dk.bjarkebjarke.tally.signin.SignInViewModel
import dk.bjarkebjarke.tally.start.StartUiState
import dk.bjarkebjarke.tally.start.StartViewModel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    private val start: StartViewModel by viewModels()
    private val signInModel: SignInViewModel by viewModels()
    private val accountModel: AccountViewModel by viewModels()

    @Inject
    lateinit var startedActivity: StartedActivity

    @Inject
    lateinit var profiles: AccountProfiles

    @Inject
    lateinit var signedOutCleanup: SignedOutCleanup

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // M1-89: once the start-up root is ready, the copy on the phone goes whenever nobody is signed in. Not before:
        // the update gate reads config/app (M1-82) through the Firestore instance that a clear terminates. Only that
        // first read is ordered: a later one (back in the app after 5 s or more) can meet the clear of Firebase's own
        // sign-out, and the root keeps its screen for up to the gate's 5 s limit.
        lifecycleScope.launch {
            start.uiState.first { it is StartUiState.Ready }
            signedOutCleanup.start()
        }
        // M1-88: Credential Manager opens Google's account picker in this activity while it is started.
        lifecycle.addObserver(startedActivity)
        enableEdgeToEdge()
        setContent {
            TallyApp(
                start,
                signIn = { SignInRoute(signInModel, onEmail = ::openEmailScreens) },
                account = { onBack -> AccountRoute(accountModel, onBack) },
                avatarInitial = { initialOf(profiles.current()) },
            )
        }
    }

    /** M1-17 opens the email screens; until then "Use email and password" does nothing. */
    private fun openEmailScreens() = Unit
}
