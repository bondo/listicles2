package dev.listicles.testing

import org.junit.platform.launcher.LauncherSession
import org.junit.platform.launcher.LauncherSessionListener

/** Registered through `META-INF/services`; opens before the first engine runs, whatever the engine order. */
class NoNetworkSessionListener : LauncherSessionListener {
    override fun launcherSessionOpened(session: LauncherSession) = NoNetwork.install()
}
