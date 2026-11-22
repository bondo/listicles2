package dk.bjarkebjarke.tally

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

/** M1-30: the root of the Hilt graph (checklist section 1: dependency injection with Hilt). */
@HiltAndroidApp
class TallyApplication : Application()
