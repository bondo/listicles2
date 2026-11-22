package dk.bjarkebjarke.tally

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import dagger.hilt.android.AndroidEntryPoint
import dk.bjarkebjarke.tally.start.StartViewModel

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    private val start: StartViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { TallyApp(start) }
    }
}
