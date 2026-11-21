import io.gitlab.arturbosch.detekt.Detekt
import java.util.Properties

// Dependabot alerts (issue 187, docs/SECURITY.md): transitive build and lint tool dependencies that have an advisory are
// raised to the first fixed version, from gradle/patched-dependencies.properties. Constraints only raise: a newer version
// that a plugin asks for still wins. scripts/dependency_floors.py checks gradle/verification-metadata.xml against the advisories.
// This block runs before the script body, so it cannot share a value with the project configurations below; both read the file.
buildscript {
    val patched =
        java.util.Properties().apply {
            file("gradle/patched-dependencies.properties").inputStream().use { load(it) }
        }
    dependencies {
        constraints {
            patched.forEach { (coordinate, version) -> add("classpath", "$coordinate:$version") }
        }
    }
}

plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.detekt)
    alias(libs.plugins.spotless)
    alias(libs.plugins.kover)
    alias(libs.plugins.licensee) apply false
    alias(libs.plugins.roborazzi) apply false
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
    detektPlugins(libs.compose.rules.detekt)
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
                    "dk.bjarkebjarke.tally.MainActivity",
                    "dk.bjarkebjarke.tally.R",
                    "dk.bjarkebjarke.tally.R$*",
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

// The same floor for every project configuration (the Android lint tool, test and build tool classpaths). Constraints cannot be
// declared on resolvable-only configurations such as compileClasspath, so the selection is raised while dependencies resolve.
val patchedDependencies =
    Properties().apply {
        file("gradle/patched-dependencies.properties").inputStream().use { load(it) }
    }

fun versionParts(version: String): List<Int> = version.substringBefore('-').split('.').map { it.toIntOrNull() ?: 0 }

fun isOlder(
    version: String,
    fixed: String,
): Boolean {
    val a = versionParts(version)
    val b = versionParts(fixed)
    for (i in 0 until maxOf(a.size, b.size)) {
        val diff = a.getOrElse(i) { 0 } - b.getOrElse(i) { 0 }
        if (diff != 0) return diff < 0
    }
    return false
}

allprojects {
    configurations.configureEach {
        resolutionStrategy.eachDependency {
            val fixed = patchedDependencies.getProperty("${requested.group}:${requested.name}")
            val wanted = requested.version
            if (fixed != null && wanted != null && isOlder(wanted, fixed)) {
                useVersion(fixed)
                because("Dependabot alert: first fixed version is $fixed (docs/SECURITY.md)")
            }
        }
    }
}

// Test-support JVM modules run only on the host JDK (21), never on Android, and use its newer API on purpose
// (:core:testing blocks the network through java.net.spi.InetAddressResolver, JDK 18). checkJdkRelease fails if any
// non-test configuration depends on one of them, so such a module can never reach the app.
val jdkTestSupportModules = setOf(":core:testing")

// Issue 211: every JVM module (Kotlin JVM plugin) compiles against the JDK 17 API, not the JDK 21 one the build runs
// on. minSdk is 26 and Android has java.util.List.removeFirst()/removeLast() only from API 35, so a call that
// resolves to the JDK 21 member crashes on Android 8 to 14. Kotlin (-Xjdk-release) and Java (--release) must both
// say 17. This closes the JDK 18 to 21 gap only: Java 9 to 17 APIs that are newer than API 26 (for example
// Stream.toList) still compile and are not checked here. The task first runs its own negative cases on the
// predicate, then checks every real compile task.
// Run: ./gradlew checkJdkRelease (wired into detekt, so verify.sh and CI run it).
val checkJdkRelease =
    tasks.register("checkJdkRelease") {
        group = "verification"
        description = "Fails if a JVM module's Kotlin or Java compile task does not target the JDK 17 API."
        val wanted = "17"

        // The last -Xjdk-release value wins, as on the Kotlin command line; a bare flag has no value.
        fun kotlinRelease(args: List<String>): String? =
            args.lastOrNull { it.startsWith("-Xjdk-release") }?.substringAfter('=', "")

        fun kotlinOk(args: List<String>) = kotlinRelease(args) == wanted

        fun javaOk(release: String) = release == wanted

        val jvmProjects =
            provider {
                allprojects.filter {
                    it.plugins.hasPlugin("org.jetbrains.kotlin.jvm") && it.path !in jdkTestSupportModules
                }
            }
        // "project path -> configuration" for every non-test configuration that depends on a test-support module.
        val leaks =
            provider {
                allprojects.flatMap { p ->
                    p.configurations
                        .filterNot { it.name.contains("test", ignoreCase = true) }
                        .flatMap { c ->
                            c.dependencies
                                .withType<ProjectDependency>()
                                .filter { it.path in jdkTestSupportModules }
                                .map { "${p.path}:${c.name} -> ${it.path}" }
                        }
                }
            }
        inputs.property("leaks", leaks)
        val kotlinTasks =
            jvmProjects.map { ps ->
                ps.flatMap { p ->
                    p.tasks
                        .withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask<*>>()
                        .map { it.path to it.compilerOptions.freeCompilerArgs.getOrElse(emptyList()) }
                }
            }
        val javaTasks =
            jvmProjects.map { ps ->
                ps.flatMap { p ->
                    p.tasks.withType<JavaCompile>().map {
                        it.path to (
                            it.options.release.orNull
                                ?.toString() ?: ""
                        )
                    }
                }
            }
        val moduleCount = jvmProjects.map { it.size }
        inputs.property("kotlinTasks", kotlinTasks)
        inputs.property("javaTasks", javaTasks)
        inputs.property("moduleCount", moduleCount)
        doLast {
            // Negative cases first: a predicate that accepts everything would make the real check pass.
            val selfTest =
                listOf(
                    kotlinOk(listOf("-Xjdk-release=17")),
                    kotlinOk(listOf("-Xfoo", "-Xjdk-release=17", "-Xbar")),
                    !kotlinOk(emptyList()),
                    !kotlinOk(listOf("-Xjdk-release=21")),
                    !kotlinOk(listOf("-Xjdk-release=1.8")),
                    !kotlinOk(listOf("-Xjdk-release=17", "-Xjdk-release=21")),
                    !kotlinOk(listOf("-Xjdk-release")),
                    !kotlinOk(listOf("-Xjdk-release=")),
                    !kotlinOk(listOf("-Xjdk-release=170")),
                    javaOk("17"),
                    !javaOk(""),
                    !javaOk("21"),
                    !javaOk("1.8"),
                )
            check(selfTest.all { it }) { "checkJdkRelease self-test failed: $selfTest" }
            check(moduleCount.get() > 0 && kotlinTasks.get().isNotEmpty() && javaTasks.get().isNotEmpty()) {
                "checkJdkRelease found no JVM module compile tasks; the check is broken"
            }
            val offenders =
                kotlinTasks.get().filterNot { (_, args) -> kotlinOk(args) }.map { (path, args) ->
                    val flags = args.filter { it.startsWith("-Xjdk-release") }.ifEmpty { listOf("no -Xjdk-release") }
                    "$path (Kotlin: $flags)"
                } +
                    javaTasks.get().filterNot { (_, release) -> javaOk(release) }.map { (path, release) ->
                        "$path (Java release: ${release.ifEmpty { "unset" }})"
                    }
            check(leaks.get().isEmpty()) {
                "test-support modules (use JDK 21 API) must only be test dependencies: ${leaks.get().joinToString()}"
            }
            check(offenders.isEmpty()) {
                "JVM modules must compile against the JDK $wanted API (-Xjdk-release=$wanted, " +
                    "options.release=$wanted), not the JDK 21 one the build runs on: Android has the JDK 18 to 21 " +
                    "API (for example List.removeFirst) only from API 35 and minSdk is 26. " +
                    "Offenders: ${offenders.joinToString()}"
            }
        }
    }

tasks.named("detekt") { dependsOn(checkJdkRelease) }

// The shared setting that checkJdkRelease checks: every JVM module compiles against the JDK 17 API.
subprojects {
    if (path in jdkTestSupportModules) return@subprojects
    plugins.withId("org.jetbrains.kotlin.jvm") {
        tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask<*>>().configureEach {
            compilerOptions.freeCompilerArgs.add("-Xjdk-release=17")
        }
        tasks.withType<JavaCompile>().configureEach { options.release.set(17) }
    }
}

// Every test JVM blocks network access (core/testing: NoNetwork). NIO sockets need the JDK's selector provider
// replaced, which is only possible through a system property read when the JVM first needs one.
subprojects {
    tasks.withType<Test>().configureEach {
        jvmArgs(
            "--add-exports=java.base/sun.nio.ch=ALL-UNNAMED",
            "-Djava.nio.channels.spi.SelectorProvider=dk.bjarkebjarke.tally.testing.BlockingSelectorProvider",
            "-Djava.nio.channels.spi.AsynchronousChannelProvider=dk.bjarkebjarke.tally.testing.BlockingAsynchronousChannelProvider",
        )
    }
}

// M0.5-10: the licensee policy (config/licensee/policy.gradle) is tested against a fixture build whose
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
        // A licensee bump must make the gate out of date (issue 216), not leave it UP-TO-DATE on the old version.
        inputs.property("licenseeVersion", pluginVersion)
        val marker = layout.buildDirectory.file("licensee-gate.ok")
        outputs.file(marker)
        val allowed = "fixture:apache:1.0,fixture:mit:1.0,fixture:bsd2:1.0,fixture:bsd3:1.0"
        val terms = "developer.android.com/studio/terms"
        val a1 = "approved-a1.txt"
        val notGoogle = "not the Google/Android SDK terms"
        val coordinates = "must be group:artifact:version"
        val cases =
            listOf(
                licenseeCase("allowed SPDX ids", allowed, passes = true),
                licenseeCase("google terms, listed artifact", "fixture:google-a:1.0", a1, passes = true),
                licenseeCase("google terms, not listed", "fixture:google-a:1.0", passes = false, message = terms),
                licenseeCase(
                    "google terms, other artifact",
                    "fixture:google-b:1.0",
                    a1,
                    passes = false,
                    message = terms,
                ),
                licenseeCase(
                    "google terms, other version",
                    "fixture:google-a:2.0",
                    a1,
                    passes = false,
                    message = terms,
                ),
                licenseeCase(
                    "entry without reason",
                    "fixture:google-a:1.0",
                    "approved-no-reason.txt",
                    passes = false,
                    message = "reason",
                ),
                // A google-sdk-terms.txt line must only cover the Google/Android SDK terms, not any licence (R1-01).
                licenseeCase(
                    "listed artifact, GPL-3.0",
                    "fixture:gpl3:1.0",
                    "approved-gpl3.txt",
                    passes = false,
                    message = notGoogle,
                ),
                licenseeCase(
                    "listed artifact, proprietary",
                    "fixture:proprietary:1.0",
                    "approved-proprietary.txt",
                    passes = false,
                    message = notGoogle,
                ),
                licenseeCase(
                    "listed artifact, no licence",
                    "fixture:nolicense:1.0",
                    "approved-nolicense.txt",
                    passes = false,
                    message = notGoogle,
                ),
                // Malformed lines are rejected (R1-02).
                licenseeCase(
                    "entry with wildcard version",
                    "fixture:google-a:1.0",
                    "approved-wild-version.txt",
                    passes = false,
                    message = coordinates,
                ),
                licenseeCase(
                    "entry without version",
                    "fixture:google-a:1.0",
                    "approved-no-version.txt",
                    passes = false,
                    message = coordinates,
                ),
                licenseeCase(
                    "entry with wildcard group",
                    "fixture:google-a:1.0",
                    "approved-wild-group.txt",
                    passes = false,
                    message = coordinates,
                ),
                licenseeCase(
                    "entry with four parts",
                    "fixture:google-a:1.0",
                    "approved-four-parts.txt",
                    passes = false,
                    message = coordinates,
                ),
                licenseeCase("allowed plus one bad", "$allowed,fixture:gpl3:1.0", passes = false, message = "gpl-3.0"),
            ) +
                listOf(
                    "gpl3" to "gpl-3.0",
                    "lgpl21" to "lgpl-2.1",
                    "agpl3" to "agpl-3.0",
                    "epl2" to "EPL-2.0",
                    "mpl2" to "MPL/2.0",
                    "proprietary" to "example.com/license",
                    "nolicense" to "declares no licenses",
                ).map { (artifact, message) ->
                    licenseeCase(
                        "disallowed licence: $artifact",
                        "fixture:$artifact:1.0",
                        passes = false,
                        message = message,
                    )
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

// Compose and extra detekt rules gate (issue 38): the fixtures under config/detekt/fixtures are never part of an
// app source set. The violating fixture must produce every expected rule; the clean one must produce nothing.
// Type-resolved fixtures (InjectDispatcher needs types) get kotlinx-coroutines on the detekt classpath.
val detektFixtureClasspath by configurations.creating { isCanBeConsumed = false }

dependencies { detektFixtureClasspath(libs.kotlinx.coroutines.core) }

fun registerFixtureDetekt(
    taskName: String,
    dirName: String,
    failOnFindings: Boolean,
    typed: Boolean = false,
) = tasks.register<Detekt>(taskName) {
    setSource(layout.projectDirectory.dir("config/detekt/fixtures/$dirName"))
    include("**/*.kt")
    buildUponDefaultConfig = true
    allRules = false
    config.setFrom("config/detekt/detekt.yml")
    ignoreFailures = !failOnFindings
    if (typed) classpath.setFrom(detektFixtureClasspath)
    reports {
        html.required.set(false)
        xml.required.set(true)
        xml.outputLocation.set(layout.buildDirectory.file("reports/detekt-fixtures/$dirName.xml"))
    }
}

// Each case: fixture directory, whether it is type-resolved, and the rules it must report ("clean" ones: none).
val detektFixtureCases =
    mapOf(
        "violating" to
            listOf(
                "ModifierMissing",
                "ComposableNaming",
                "MutableStateParam",
                "ParameterNaming",
                "ComposableParamOrder",
                "GlobalCoroutineUsage",
                "Material2",
                "LongParameterList",
            ),
        "violating-typed" to listOf("InjectDispatcher"),
        "clean" to emptyList(),
        "clean-typed" to emptyList(),
    )
val detektFixtureTasks =
    detektFixtureCases.keys.map { dir ->
        registerFixtureDetekt(
            taskName = "detektFixture" + dir.split('-').joinToString("") { it.replaceFirstChar(Char::uppercase) },
            dirName = dir,
            failOnFindings = !dir.startsWith("violating"),
            typed = dir.endsWith("-typed"),
        )
    }

val testDetektRules =
    tasks.register("testDetektRules") {
        group = "verification"
        description = "Compose and extra detekt rules fire on the violating fixtures and stay quiet on the clean ones."
        dependsOn(detektFixtureTasks)
        val fixtureRoot = layout.projectDirectory.dir("config/detekt/fixtures")
        val reportDir = layout.buildDirectory.dir("reports/detekt-fixtures")
        val cases = detektFixtureCases
        doLast {
            val ruleId = Regex("source=\"detekt\\.(?:[A-Za-z-]+[:.])?([A-Za-z0-9]+)\"")
            val problems = mutableListOf<String>()
            for ((dir, expected) in cases) {
                val count =
                    fixtureRoot
                        .dir(dir)
                        .asFile
                        .walkTopDown()
                        .count { it.extension == "kt" }
                if (count == 0) problems += "$dir: no Kotlin files; the gate is broken"
                val report =
                    reportDir
                        .get()
                        .file("$dir.xml")
                        .asFile
                        .readText()
                val found = ruleId.findAll(report).map { it.groupValues[1] }.toSet()
                if (dir.startsWith("clean")) {
                    if (found.isNotEmpty()) problems += "$dir: unexpected findings $found"
                } else {
                    val missing = expected.filter { it !in found }
                    if (missing.isNotEmpty()) problems += "$dir: did not report $missing (found $found)"
                }
            }
            check(problems.isEmpty()) { "detekt rules gate:\n" + problems.joinToString("\n") }
        }
    }

// Shipped modules only: :core:testing is test support (never in the app), consumed via testImplementation.
tasks.named("detekt") { dependsOn(testLicenseeGate, testDetektRules, ":app:licensee", ":core:domain:licensee") }

// M1-05: CI's unit job calls koverVerify, so PIT on core/domain rides along without a separate workflow step.
tasks.named("koverVerify") { dependsOn(":core:domain:pitest") }
