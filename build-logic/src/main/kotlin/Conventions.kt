import com.android.build.api.dsl.CommonExtension
import org.gradle.api.JavaVersion
import org.gradle.api.Project
import org.gradle.api.artifacts.VersionCatalogsExtension
import org.gradle.api.plugins.JavaPluginExtension
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test
import org.gradle.kotlin.dsl.apply
import org.gradle.kotlin.dsl.configure
import org.gradle.kotlin.dsl.getByType
import org.gradle.kotlin.dsl.withType
import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import org.jetbrains.kotlin.gradle.dsl.KotlinAndroidProjectExtension
import org.jetbrains.kotlin.gradle.dsl.KotlinJvmCompilerOptions
import org.jetbrains.kotlin.gradle.dsl.KotlinJvmProjectExtension
import org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask

// The one copy of the settings every module shares (#217 item 1). The root build's checkWarningsAsErrors and
// checkJdkRelease check the result for every compile task.

private const val COMPILE_SDK = 37
private const val MIN_SDK = 26
private const val JDK_RELEASE = 17
private const val TEST_SUPPORT = ":core:testing"
private const val SPI = "-Djava.nio.channels.spi"
private const val BLOCKING = "dk.bjarkebjarke.tally.testing.Blocking"

/** Java and Kotlin 17, warnings as errors (M0.5-09) and the test-JVM network block for every module. */
internal fun Project.configureKotlinModule(compilerOptions: KotlinJvmCompilerOptions) {
    pluginManager.apply(DependencyFloorsPlugin::class)
    // On the extension, as before: these are the conventions of every compile task of the module.
    compilerOptions.jvmTarget.set(JvmTarget.JVM_17)
    compilerOptions.allWarningsAsErrors.set(true)
    // Every test JVM blocks network access (core/testing: NoNetwork). NIO sockets need the JDK's selector provider
    // replaced, which is only possible through a system property read when the JVM first needs one.
    tasks.withType<Test>().configureEach {
        jvmArgs(
            "--add-exports=java.base/sun.nio.ch=ALL-UNNAMED",
            "$SPI.SelectorProvider=${BLOCKING}SelectorProvider",
            "$SPI.AsynchronousChannelProvider=${BLOCKING}AsynchronousChannelProvider",
        )
    }
    // #217 item 3: the flags above name classes of :core:testing, so every test classpath gets it, in the same place
    // (a new module included; the existing ones also declare it, which check_ui_emulators.py reads for :core:data).
    if (path != TEST_SUPPORT) {
        dependencies.add("testImplementation", dependencies.project(mapOf("path" to TEST_SUPPORT)))
    }
}

/** A Kotlin JVM module: the shared settings, detekt with the project config, and (unless test support) JDK 17 API. */
internal fun Project.configureJvmModule(jdkRelease: Boolean) {
    pluginManager.apply("org.jetbrains.kotlin.jvm")
    pluginManager.apply("io.gitlab.arturbosch.detekt")
    extensions.configure<JavaPluginExtension> {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    configureKotlinModule(extensions.getByType<KotlinJvmProjectExtension>().compilerOptions)
    extensions.configure<io.gitlab.arturbosch.detekt.extensions.DetektExtension> {
        // Type-resolved tasks (detektMain, detektTest); the root task covers all sources without types.
        buildUponDefaultConfig = true
        config.setFrom(isolated.rootProject.projectDirectory.file("config/detekt/detekt.yml"))
    }
    val libs = extensions.getByType<VersionCatalogsExtension>().named("libs")
    dependencies.add("detektPlugins", libs.findLibrary("compose-rules-detekt").get())
    // Issue 211: JVM modules compile against the JDK 17 API, not the JDK 21 one the build runs on (checkJdkRelease).
    // Test-support modules run only on the host JDK and use its newer API on purpose.
    if (jdkRelease) {
        val kotlinCompiles = tasks.withType<KotlinCompilationTask<*>>()
        kotlinCompiles.configureEach { compilerOptions.freeCompilerArgs.add("-Xjdk-release=$JDK_RELEASE") }
        tasks.withType<JavaCompile>().configureEach { options.release.set(JDK_RELEASE) }
    }
}

/** An Android module (application or library): compileSdk, minSdk, Java 17 and the shared Kotlin settings. */
internal fun Project.configureAndroidModule(pluginId: String) {
    pluginManager.apply(pluginId)
    extensions.configure<CommonExtension> {
        compileSdk = COMPILE_SDK
        defaultConfig.minSdk = MIN_SDK
        defaultConfig.testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        compileOptions.sourceCompatibility = JavaVersion.VERSION_17
        compileOptions.targetCompatibility = JavaVersion.VERSION_17
    }
    configureKotlinModule(extensions.getByType<KotlinAndroidProjectExtension>().compilerOptions)
}
