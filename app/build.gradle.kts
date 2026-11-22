import org.gradle.process.CommandLineArgumentProvider

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kover)
    alias(libs.plugins.licensee)
    alias(libs.plugins.roborazzi)
}

// M0.5-10: shipped dependencies must be on the owner's licence allowlist.
apply(from = rootProject.file("config/licensee/policy.gradle"))

android {
    namespace = "dk.bjarkebjarke.tally"
    compileSdk = 37

    defaultConfig {
        applicationId = "dk.bjarkebjarke.tally"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "0.0.1"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.all { it.useJUnitPlatform() }
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
    // A test task that discovers zero tests is a failure, not a pass.
    failOnNoDiscoveredTests = true
    if (name == "testDebugUnitTest") finalizedBy(checkUnitTestResults)
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        allWarningsAsErrors.set(true)
    }
}

dependencies {
    implementation(project(":core:domain"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.compose.ui.tooling.preview)
    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)

    testImplementation(platform(libs.junit.bom))
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.junit4)
    testImplementation(libs.kotest.assertions)
    testImplementation(project(":core:testing"))
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
            }
        }
        verify {
            rule("app line coverage") {
                minBound(80)
            }
        }
    }
}
