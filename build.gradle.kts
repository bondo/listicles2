import io.gitlab.arturbosch.detekt.Detekt

plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.detekt)
    alias(libs.plugins.spotless)
    alias(libs.plugins.kover)
    alias(libs.plugins.licensee) apply false
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
val checkWarningsAsErrors =
    tasks.register("checkWarningsAsErrors") {
        group = "verification"
        description = "Fails if any Kotlin compile task does not set allWarningsAsErrors or hides warnings."
        // Evaluated lazily (when the task graph is built), after every project has been configured.
        val compileTasks =
            provider {
                allprojects.flatMap { p ->
                    p.tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask<*>>().toList()
                }
            }

        // Flags that turn warnings off or hide them, which would bypass allWarningsAsErrors.
        // A bare flag takes the next element as its value, so check the list as a sequence.
        fun hidesWarnings(args: List<String>): Boolean =
            args.withIndex().any { (i, arg) ->
                val value =
                    if (arg.contains('=')) arg.substringAfter('=') else args.getOrNull(i + 1).orEmpty()
                // The value is a comma-separated list; every entry must raise its diagnostic to an error.
                val allErrors =
                    value.split(',').map { it.trim() }.filter { it.isNotEmpty() }.let { entries ->
                        entries.isNotEmpty() && entries.all { it.endsWith(":error") }
                    }
                arg == "-nowarn" ||
                    arg.startsWith("-Xsuppress-warning") ||
                    (arg.startsWith("-Xwarning-level") && !allErrors)
            }
        val offenders =
            compileTasks.map { all ->
                all
                    .filter {
                        val o = it.compilerOptions
                        !o.allWarningsAsErrors.getOrElse(false) ||
                            o.suppressWarnings.getOrElse(false) ||
                            hidesWarnings(o.freeCompilerArgs.getOrElse(emptyList()))
                    }.map { it.path }
            }
        val taskCount = compileTasks.map { it.size }
        inputs.property("offenders", offenders)
        inputs.property("taskCount", taskCount)
        doLast {
            check(taskCount.get() > 0) { "checkWarningsAsErrors found no Kotlin compile tasks; the check is broken" }
            check(offenders.get().isEmpty()) {
                "warnings are not all errors (allWarningsAsErrors off, suppressWarnings, -nowarn, " +
                    "-Xsuppress-warning, -Xwarning-level=...:disabled/warning/info) for: ${offenders.get().joinToString()}"
            }
        }
    }

tasks.named("detekt") { dependsOn(checkWarningsAsErrors) }

// Every test JVM blocks network access (core/testing: NoNetwork). NIO sockets need the JDK's selector provider
// replaced, which is only possible through a system property read when the JVM first needs one.
subprojects {
    tasks.withType<Test>().configureEach {
        jvmArgs(
            "--add-exports=java.base/sun.nio.ch=ALL-UNNAMED",
            "-Djava.nio.channels.spi.SelectorProvider=dev.listicles.testing.BlockingSelectorProvider",
            "-Djava.nio.channels.spi.AsynchronousChannelProvider=dev.listicles.testing.BlockingAsynchronousChannelProvider",
        )
    }
}

// M0.5-10: the licensee policy (config/licensee/policy.gradle.kts) is tested against a fixture build whose
// artifacts have chosen licences. Each case runs the fixture's `licensee` task: it must pass for the owner's
// allowlist and fail, naming the artifact, for any other licence. Wired into detekt, so verify.sh and CI run it.
// A case is one string, "name|deps|approved|pass or fail|text the output must contain", so the task stays
// configuration-cache friendly (no script object references).
fun licenseeCase(
    name: String,
    deps: String,
    approved: String = "",
    passes: Boolean,
    message: String = "",
) = listOf(name, deps, approved, if (passes) "pass" else "fail", message).joinToString("|")

val testLicenseeGate =
    tasks.register("testLicenseeGate") {
        group = "verification"
        description = "Runs the licensee policy against fixture artifacts with allowed and disallowed licences."
        val fixture = layout.projectDirectory.dir("config/licensee/fixture").asFile
        val wrapper = layout.projectDirectory.file("gradlew").asFile
        val pluginVersion = libs.versions.licensee.get()
        inputs.dir(layout.projectDirectory.dir("config/licensee"))
        val marker = layout.buildDirectory.file("licensee-gate.ok")
        outputs.file(marker)
        val allowed = "fixture:apache:1.0,fixture:mit:1.0,fixture:bsd2:1.0,fixture:bsd3:1.0"
        val cases =
            listOf(
                licenseeCase("allowed SPDX ids", allowed, passes = true),
                licenseeCase("google terms, listed artifact", "fixture:google-a:1.0", "approved-a1.txt", passes = true),
                licenseeCase("google terms, not listed", "fixture:google-a:1.0", passes = false, message = "google-a"),
                licenseeCase(
                    "google terms, other artifact",
                    "fixture:google-b:1.0",
                    "approved-a1.txt",
                    passes = false,
                    message = "google-b",
                ),
                licenseeCase(
                    "google terms, other version",
                    "fixture:google-a:2.0",
                    "approved-a1.txt",
                    passes = false,
                    message = "google-a",
                ),
                licenseeCase(
                    "listed entry without reason",
                    "fixture:google-a:1.0",
                    "approved-no-reason.txt",
                    passes = false,
                    message = "reason",
                ),
                licenseeCase("allowed plus one bad", "$allowed,fixture:gpl3:1.0", passes = false, message = "gpl3"),
            ) +
                listOf("gpl3", "lgpl21", "agpl3", "epl2", "mpl2", "proprietary", "nolicense").map {
                    licenseeCase("disallowed licence: $it", "fixture:$it:1.0", passes = false, message = it)
                }

        doLast {
            val problems = mutableListOf<String>()
            for (line in cases) {
                val (name, deps, approved, expected, message) = line.split('|')
                val passes = expected == "pass"
                val command =
                    mutableListOf(
                        wrapper.path,
                        "-q",
                        "--console=plain",
                        "--no-daemon",
                        "-p",
                        fixture.path,
                        "-Dlicensee.version=$pluginVersion",
                        "-Pdeps=$deps",
                    )
                if (approved.isNotEmpty()) command += "-Papproved=$approved"
                command += "licensee"
                var out = ""
                var code = 0
                // Retry only Maven 429 (rate limit), so a throttled plugin download is not read as a result.
                for (attempt in 1..5) {
                    val process = ProcessBuilder(command).directory(fixture).redirectErrorStream(true).start()
                    out = process.inputStream.bufferedReader().readText()
                    code = process.waitFor()
                    if (!(out.contains("429") && out.contains("Too Many Requests")) || attempt == 5) break
                    Thread.sleep(10_000L * attempt)
                }
                val ok = (code == 0) == passes && out.contains(message)
                if (!ok) {
                    val shown = out.lines().filter { it.isNotBlank() && !it.startsWith("Picked up") }.take(8)
                    problems += "$name: expected $expected, exit $code\n" +
                        shown.joinToString("\n") { "    $it" }
                }
            }
            check(
                problems.isEmpty(),
            ) { "licensee gate: ${problems.size} case(s) wrong:\n" + problems.joinToString("\n") }
            marker.get().asFile.writeText("ok\n")
        }
    }
