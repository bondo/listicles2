import org.gradle.api.Plugin
import org.gradle.api.Project

/** listicles.jvm.library: a pure Kotlin JVM module that may reach the app (JDK 17 API). */
class JvmLibraryConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) = target.configureJvmModule(jdkRelease = true)
}

/** listicles.jvm.testsupport: a test-only JVM module (host JDK API; checkJdkRelease keeps it out of shipped code). */
class JvmTestSupportConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) = target.configureJvmModule(jdkRelease = false)
}

class AndroidLibraryConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) = target.configureAndroidModule("com.android.library")
}

class AndroidApplicationConventionPlugin : Plugin<Project> {
    override fun apply(target: Project) = target.configureAndroidModule("com.android.application")
}
