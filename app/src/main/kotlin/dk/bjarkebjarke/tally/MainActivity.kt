package dk.bjarkebjarke.tally

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import dagger.hilt.android.AndroidEntryPoint
import dk.bjarkebjarke.tally.domain.session.SignedOutCleanup
import dk.bjarkebjarke.tally.session.StartedActivity
import dk.bjarkebjarke.tally.start.StartViewModel
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    private val start: StartViewModel by viewModels()

    @Inject
    lateinit var startedActivity: StartedActivity

    @Inject
    lateinit var signedOutCleanup: SignedOutCleanup

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // M1-89: from the first start on, the copy on the phone goes whenever nobody is signed in.
        signedOutCleanup.start()
        // M1-88: Credential Manager opens Google's account picker in this activity while it is started.
        lifecycle.addObserver(startedActivity)
        enableEdgeToEdge()
        setContent { TallyApp(start) }
    }
}
