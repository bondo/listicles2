package dk.bjarkebjarke.tally.session

import android.app.Activity
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import dk.bjarkebjarke.tally.data.session.ForegroundActivity
import javax.inject.Inject
import javax.inject.Singleton

/**
 * MainActivity while it is started (M1-88), for Credential Manager's account picker: the picker needs an activity
 * context, so it opens in the app's task. MainActivity adds this observer to its own lifecycle, so the picker's own
 * translucent activity, which opens above it and closes again, does not count. Application-wide activity callbacks
 * would see that one too: its stop would clear this while MainActivity, only paused under it, stays started, and the
 * next sign-in would find no activity. The callbacks run on the main thread; the picker may read [current] from
 * another one.
 */
@Singleton
class StartedActivity
    @Inject
    constructor() :
    ForegroundActivity,
        DefaultLifecycleObserver {
        @Volatile
        private var started: Activity? = null

        override fun current(): Activity? = started

        override fun onStart(owner: LifecycleOwner) {
            started = owner as? Activity
        }

        /** Only its own stop clears it: a second MainActivity (a new task, say) starts before the first one stops. */
        override fun onStop(owner: LifecycleOwner) {
            if (started === owner) started = null
        }
    }
