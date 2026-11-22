package dk.bjarkebjarke.tally

import android.app.Application
import com.google.firebase.appcheck.AppCheckProviderFactory
import com.google.firebase.appcheck.FirebaseAppCheck
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject

/** M1-30: the root of the Hilt graph (checklist section 1: dependency injection with Hilt). */
@HiltAndroidApp
class TallyApplication : Application() {
    @Inject
    lateinit var appCheckFactory: AppCheckProviderFactory

    override fun onCreate() {
        super.onCreate()
        // M1-26: before any Firebase call; the graph picks the debug or the Play Integrity factory per build type.
        FirebaseAppCheck.getInstance().installAppCheckProviderFactory(appCheckFactory)
    }
}
