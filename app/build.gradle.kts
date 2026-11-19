plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kover)
    alias(libs.plugins.licensee)
}

// M0.5-10: shipped dependencies must be on the owner's licence allowlist.
apply(from = rootProject.file("config/licensee/policy.gradle"))

android {
    namespace = "dev.listicles.app"
    compileSdk = 37

    defaultConfig {
        applicationId = "dev.listicles.app"
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
    }

    buildFeatures {
        compose = true
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

    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.compose.ui.test.junit4)
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
                    "dev.listicles.app.MainActivity",
                    "dev.listicles.app.R",
                    "dev.listicles.app.R$*",
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
