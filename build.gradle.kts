import io.gitlab.arturbosch.detekt.Detekt

plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.detekt)
    alias(libs.plugins.spotless)
    alias(libs.plugins.kover)
}

spotless {
    kotlin {
        target("**/src/**/*.kt")
        ktlint(libs.versions.ktlint.get())
    }
    kotlinGradle {
        target("*.gradle.kts", "**/*.gradle.kts")
        targetExclude("**/build/**")
        ktlint(libs.versions.ktlint.get())
    }
}

detekt {
    buildUponDefaultConfig = true
    allRules = false
    config.setFrom("config/detekt/detekt.yml")
    // No baseline: findings must be fixed, not recorded. scripts/guards.sh enforces this.
    source.setFrom(
        fileTree(rootDir) {
            include("**/src/**/*.kt")
            exclude("**/build/**")
        },
    )
}

tasks.withType<Detekt>().configureEach {
    jvmTarget = "17"
    reports {
        html.required.set(true)
        txt.required.set(false)
        sarif.required.set(false)
        md.required.set(false)
        xml.required.set(false)
    }
}

dependencies {
    kover(project(":app"))
    kover(project(":core:domain"))
}

kover {
    reports {
        filters {
            excludes {
                // Same exclusions as app/build.gradle.kts (the aggregate report does not inherit them).
                annotatedBy("androidx.compose.runtime.Composable", "androidx.compose.ui.tooling.preview.Preview")
                classes(
                    "dev.listicles.app.MainActivity",
                    "dev.listicles.app.R",
                    "dev.listicles.app.R$*",
                    "*ComposableSingletons*",
                )
            }
        }
        verify {
            // Overall floor. Per-module floors live in each module's build file.
            rule("overall line coverage") {
                minBound(80)
            }
        }
    }
}

// M0.5-09: every Kotlin compile task (all modules, all variants, tests included) must treat warnings as errors.
// Run: ./gradlew checkWarningsAsErrors (wired into detekt, so verify.sh and CI run it).
val checkWarningsAsErrors by tasks.registering {
    group = "verification"
    description = "Fails if any Kotlin compile task does not set allWarningsAsErrors."
    // Evaluated lazily (when the task graph is built), after every project has been configured.
    val compileTasks =
        provider {
            allprojects.flatMap { p ->
                p.tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask<*>>().toList()
            }
        }
    val offenders =
        compileTasks.map { all ->
            all.filter { !it.compilerOptions.allWarningsAsErrors.getOrElse(false) }.map { it.path }
        }
    val taskCount = compileTasks.map { it.size }
    inputs.property("offenders", offenders)
    inputs.property("taskCount", taskCount)
    doLast {
        check(taskCount.get() > 0) { "checkWarningsAsErrors found no Kotlin compile tasks; the check is broken" }
        check(offenders.get().isEmpty()) {
            "allWarningsAsErrors is not enabled for: ${offenders.get().joinToString()}"
        }
    }
}

tasks.named("detekt") { dependsOn(checkWarningsAsErrors) }
