import com.google.gms.googleservices.GoogleServicesTask
import org.gradle.api.artifacts.result.ResolvedComponentResult
import org.gradle.api.artifacts.result.ResolvedDependencyResult
import org.gradle.process.CommandLineArgumentProvider

plugins {
    alias(libs.plugins.listicles.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kover)
    alias(libs.plugins.licensee)
    alias(libs.plugins.roborazzi)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
    alias(libs.plugins.google.services)
}

// M0.5-10: shipped dependencies must be on the owner's licence allowlist.
apply(from = rootProject.file("config/licensee/policy.gradle"))

android {
    namespace = "dk.bjarkebjarke.tally"

    defaultConfig {
        applicationId = "dk.bjarkebjarke.tally"
        targetSdk = 37
        versionCode = 1
        versionName = "0.0.1"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    testOptions {
        // RenameTest reads the merged manifest and string resources.
        unitTests.isIncludeAndroidResources = true
    }

    buildFeatures {
        compose = true
    }

    // M1-24 (LANG-02): the per-app language picker (Android 13+) offers the languages of values/ and values-da/.
    androidResources {
        generateLocaleConfig = true
    }

    lint {
        warningsAsErrors = true
        abortOnError = true
        checkDependencies = true
        // Missing Danish (or English) strings fail the build.
        error += "MissingTranslation"
        // Dependency freshness is handled by Dependabot, not by failing PRs.
        disable += // justified: dependency freshness is Dependabot's job
            setOf(
                "GradleDependency",
                "NewerVersionAvailable",
                "AndroidGradlePluginVersion",
            )
    }
}

// M1-30 (M1.md section 1): the real google-services.json is never committed; the owner keeps it at app/ (M1-O1). Without
// it every variant gets a demo-tally stand-in with dummy values under build/ (GoogleServicesConfigTest checks which).
val googleServicesStandIn =
    !file("google-services.json").exists() && fileTree("src") { include("*/google-services.json") }.isEmpty

abstract class GoogleServicesStandIn : DefaultTask() {
    @get:Input abstract val packageName: Property<String>

    @get:OutputFile abstract val jsonFile: RegularFileProperty

    @TaskAction
    fun write() {
        val client =
            """{"client_info": {"mobilesdk_app_id": "1:000000000000:android:0000000000000000", """ +
                """"android_client_info": {"package_name": "${packageName.get()}"}}, """ +
                """"oauth_client": [], "api_key": [{"current_key": "stand-in-not-a-key"}], "services": {}}"""
        jsonFile.get().asFile.writeText(
            """{"project_info": {"project_number": "000000000000", "project_id": "demo-tally"}, """ +
                """"client": [$client], "configuration_version": "1"}""",
        )
    }
}

// PR 304 R1-02: packaging a non-debug variant with the stand-in fails unless -Ptally.allowStandInRelease=true (M1-33's
// CI smoke build); compiling release (Kover) still works. Tested by scripts/test_google_services_release_gate.py.
val allowStandInRelease = providers.gradleProperty("tally.allowStandInRelease").orNull == "true"

abstract class RefuseGoogleServicesStandIn : DefaultTask() {
    @get:Input abstract val variantName: Property<String>

    @TaskAction
    fun refuse(): Unit =
        throw GradleException(
            "The ${variantName.get()} build has no google-services.json and would ship the demo-tally stand-in. " +
                "Add the real app/google-services.json (M1-O1), or pass -Ptally.allowStandInRelease=true " +
                "for a CI smoke build (M1-33).",
        )
}

if (googleServicesStandIn) {
    // Runs after the plugin's own onVariants callback, so this replaces its search paths. One stand-in per variant: the
    // plugin looks for a client with exactly the variant's application id.
    androidComponents.onVariants { variant ->
        val name = variant.name.replaceFirstChar(Char::uppercase)
        val standIn =
            tasks.register<GoogleServicesStandIn>("googleServicesStandIn$name") {
                packageName.set(variant.applicationId)
                jsonFile.set(
                    layout.buildDirectory.file("google-services-stand-in/${variant.name}/google-services.json"),
                )
            }
        tasks.named<GoogleServicesTask>("process${name}GoogleServices") {
            dependsOn(standIn)
            googleServicesJsonFiles.set(standIn.map { listOf(it.jsonFile.get().asFile) })
        }
        if (variant.buildType != "debug" && !allowStandInRelease) {
            val refuse =
                tasks.register<RefuseGoogleServicesStandIn>("refuseGoogleServicesStandIn$name") {
                    variantName.set(variant.name)
                }
            tasks.matching { it.name == "package$name" || it.name == "package${name}Bundle" }.configureEach {
                dependsOn(refuse)
            }
        }
    }
}

// M1-26 (R5, PR 317 R1-03): the debug App Check provider must never ship. It is only a debugImplementation dependency;
// this fails every release build when it is on the release runtime classpath anyway. The self-test property puts it
// there to prove the check fails (scripts/test_google_services_release_gate.py).
if (providers.gradleProperty("tally.selfTestDebugAppCheckInRelease").orNull == "true") {
    dependencies.add("releaseImplementation", libs.firebase.appcheck.debug)
}

abstract class CheckNoDebugAppCheckInRelease : DefaultTask() {
    @get:Input abstract val releaseModules: ListProperty<String>

    @TaskAction
    fun check() {
        val found = releaseModules.get().filter { it == "com.google.firebase:firebase-appcheck-debug" }
        if (found.isNotEmpty()) {
            throw GradleException(
                "com.google.firebase:firebase-appcheck-debug is on the release runtime classpath " +
                    "(M1-26, R5).",
            )
        }
    }
}

val checkNoDebugAppCheckInRelease by tasks.registering(CheckNoDebugAppCheckInRelease::class) {
    releaseModules.set(
        configurations
            .named("releaseRuntimeClasspath")
            .flatMap { it.incoming.resolutionResult.rootComponent }
            .map { root ->
                val seen = mutableSetOf<ResolvedComponentResult>()
                val pending = ArrayDeque(listOf(root))
                while (pending.isNotEmpty()) {
                    val next = pending.removeFirst()
                    if (seen.add(next)) {
                        val dependencies = next.dependencies.filterIsInstance<ResolvedDependencyResult>()
                        pending.addAll(dependencies.map { it.selected })
                    }
                }
                seen.mapNotNull { it.moduleVersion?.let { id -> "${id.group}:${id.name}" } }
            },
    )
}

tasks.matching { it.name == "preReleaseBuild" }.configureEach { dependsOn(checkNoDebugAppCheckInRelease) }

// Issue 213: Robolectric downloads its android-all jar at test runtime unless it is told where the jar is, and the
// test JVM blocks the network (core/testing). So Gradle resolves the jar (verified by gradle/verification-metadata.xml)
// and copies it to a directory, and every test JVM runs Robolectric offline from there. A missing jar fails the test.
val robolectricAndroidAll by configurations.creating {
    isCanBeConsumed = false
    isCanBeResolved = true
}

val robolectricAndroidAllDir = layout.buildDirectory.dir("robolectric-android-all")

val syncRobolectricAndroidAll by tasks.registering(Sync::class) {
    from(robolectricAndroidAll)
    into(robolectricAndroidAllDir)
}

class RobolectricOfflineArgs(
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE) val dependencyDir: Provider<Directory>,
    @get:Input val targetSdk: Int,
) : CommandLineArgumentProvider {
    override fun asArguments() =
        listOf(
            "-Drobolectric.offline=true",
            "-Drobolectric.dependency.dir=${dependencyDir.get().asFile.absolutePath}",
            // RobolectricUnderNetworkBlockTest checks that Robolectric's SDK level (robolectric.properties) follows it.
            "-Dtally.targetSdk=$targetSdk",
        )
}

// The tokens file is an input by content (an edited token re-runs the test) and its absolute path stays out of the cache key.
class TokensArgs(
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) val tokensFile: RegularFile,
) : CommandLineArgumentProvider {
    override fun asArguments() = listOf("-Dtally.tokensFile=${tokensFile.asFile.absolutePath}")
}

tasks.withType<Test>().configureEach {
    // M1-03: the goldens are an input, or a test task that is UP-TO-DATE (or cached) after a golden changed would let
    // `scripts/screenshots.sh verify` pass without comparing anything. A file tree, not dir(..): a missing directory
    // is then an empty input instead of a validation error. scripts/check_screenshots.py checks this line.
    inputs
        .files(fileTree("src/test/screenshots"))
        .withPropertyName("screenshotGoldens")
        .withPathSensitivity(PathSensitivity.RELATIVE)
    // M1-04: ThemeTokensTest reads design/tokens.json; see TokensArgs. scripts/check_screenshots.py checks this wiring.
    jvmArgumentProviders.add(
        TokensArgs(rootProject.layout.projectDirectory.file("design/tokens.json")),
    )
    dependsOn(syncRobolectricAndroidAll)
    jvmArgumentProviders.add(
        RobolectricOfflineArgs(robolectricAndroidAllDir, checkNotNull(android.defaultConfig.targetSdk)),
    )
}

// A JUnit 4 test with no result XML was silently skipped: fail the build (issue #212).
val gateScript = rootProject.file("scripts/check_test_results.py").path
val gateSources =
    layout.projectDirectory
        .dir("src/test")
        .asFile.path
val gateResults =
    layout.buildDirectory
        .dir("test-results/testDebugUnitTest")
        .get()
        .asFile.path
// A filtered run (--tests, or one class from the IDE) runs a subset on purpose, so the gate does not apply.
val filteredTestRun =
    gradle.startParameter.taskRequests.any { request ->
        request.args.any { it == "--tests" || it.startsWith("--tests=") }
    }
val checkUnitTestResults by tasks.registering(Exec::class) {
    commandLine(
        listOf("python3", "-I", gateScript, gateSources, gateResults) +
            listOfNotNull("--filtered".takeIf { filteredTestRun }),
    )
}

tasks.withType<Test>().configureEach {
    systemProperty("tally.googleServicesStandIn", googleServicesStandIn)
    if (name == "testDebugUnitTest") finalizedBy(checkUnitTestResults)
}

dependencies {
    implementation(project(":core:domain"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.navigation3.runtime)
    implementation(libs.androidx.navigation3.ui)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.compose.ui.tooling.preview)
    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.appcheck)
    // M1-26 (R5): Play Integrity in release, the debug provider in debug builds; neither is enforced yet (M1-O4).
    releaseImplementation(libs.firebase.appcheck.playintegrity)
    debugImplementation(libs.firebase.appcheck.debug)
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)

    testImplementation(platform(libs.junit.bom))
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.junit4)
    testImplementation(libs.kotest.assertions)
    testImplementation(libs.hilt.android.testing)
    kspTest(libs.hilt.compiler)
    testRuntimeOnly(libs.junit.vintage.engine)
    testRuntimeOnly(libs.junit.platform.launcher)
    testImplementation(libs.robolectric)
    testImplementation(libs.roborazzi)
    testImplementation(libs.roborazzi.compose)
    testImplementation(libs.compose.ui.test.junit4)
    testImplementation(libs.androidx.test.espresso.core)
    robolectricAndroidAll(libs.robolectric.android.all)

    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.compose.ui.test.junit4)
    androidTestImplementation(libs.compose.ui.test.junit4.accessibility)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.androidx.test.runner)
}

kover {
    reports {
        filters {
            excludes {
                // UI is covered by Compose UI tests and screenshot tests, not by JVM line coverage.
                annotatedBy("androidx.compose.runtime.Composable", "androidx.compose.ui.tooling.preview.Preview")
                // Android entry points and generated classes have no JVM-testable logic.
                classes(
                    "dk.bjarkebjarke.tally.MainActivity",
                    "dk.bjarkebjarke.tally.R",
                    "dk.bjarkebjarke.tally.R$*",
                    "*ComposableSingletons*",
                )
                // M1-30: Hilt's generated injectors, factories and aggregation markers; AppGraphTest checks the graph instead.
                classes( // justified: Hilt-generated code holds no hand-written logic
                    "dk.bjarkebjarke.tally.Hilt_*",
                    "dk.bjarkebjarke.tally.*_Factory",
                    "dk.bjarkebjarke.tally.*_GeneratedInjector",
                    "hilt_aggregated_deps.*",
                    "dagger.hilt.internal.aggregatedroot.codegen.*",
                )
            }
        }
        verify {
            rule("app line coverage") {
                minBound(80)
            }
        }
    }
}
