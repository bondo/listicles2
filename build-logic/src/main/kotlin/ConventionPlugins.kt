import org.gradle.api.Plugin
import org.gradle.api.Project

/** tally.jvm.library: a pure Kotlin JVM module that may reach the app (JDK 17 API). */
class JvmLibraryConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) = target.configureJvmModule(jdkRelease = true)
}

/** tally.jvm.testsupport: a test-only JVM module (host JDK API; checkJdkRelease keeps it out of shipped code). */
class JvmTestSupportConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) {
        // PR 349 R1-01: the plugin skips the JDK 17 compile check, so only a listed test-support module may use it.
        check(target.path in TestSupportModules.paths) {
            "tally.jvm.testsupport is only for the test-support modules ${TestSupportModules.paths}, " +
                "not ${target.path} (add it to TestSupportModules in Conventions.kt, or use tally.jvm.library)"
        }
        target.configureJvmModule(jdkRelease = false)
    }
}

class AndroidLibraryConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) = target.configureAndroidModule("com.android.library")
}

class AndroidApplicationConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) = target.configureAndroidModule("com.android.application")
}
