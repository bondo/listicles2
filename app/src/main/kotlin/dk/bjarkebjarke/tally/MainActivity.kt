package dk.bjarkebjarke.tally

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import dagger.hilt.android.AndroidEntryPoint
import dk.bjarkebjarke.tally.session.StartedActivity
import dk.bjarkebjarke.tally.signin.SignInRoute
import dk.bjarkebjarke.tally.signin.SignInViewModel
import dk.bjarkebjarke.tally.start.StartViewModel
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    private val start: StartViewModel by viewModels()
    private val signInModel: SignInViewModel by viewModels()

    @Inject
    lateinit var startedActivity: StartedActivity

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // M1-88: Credential Manager opens Google's account picker in this activity while it is started.
        lifecycle.addObserver(startedActivity)
        enableEdgeToEdge()
        setContent { TallyApp(start, signIn = { SignInRoute(signInModel, onEmail = ::openEmailScreens) }) }
    }

    /** M1-17 opens the email screens; until then "Use email and password" does nothing. */
    private fun openEmailScreens() = Unit
}
