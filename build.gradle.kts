import io.gitlab.arturbosch.detekt.Detekt

// Dependabot alerts (issue 187, docs/SECURITY.md): transitive build and lint tool dependencies that have an advisory are
// raised to the first fixed version, from gradle/patched-dependencies.properties. Constraints only raise: a newer version
// that a plugin asks for still wins. scripts/dependency_floors.py checks gradle/verification-metadata.xml against the advisories.
// This block runs before the script body; the tally.dependency.floors plugin (build-logic) reads the same file for every
// project configuration, here and in each module.
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
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.detekt)
    alias(libs.plugins.spotless)
    alias(libs.plugins.kover)
    alias(libs.plugins.licensee) apply false
    alias(libs.plugins.roborazzi) apply false
    alias(libs.plugins.google.services) apply false
    alias(libs.plugins.hilt) apply false
    alias(libs.plugins.ksp) apply false
    alias(libs.plugins.tally.dependency.floors)
}

// M0.5-09, issue 211 and M1-68 part B2 (issue 48): checkWarningsAsErrors and checkJdkRelease are each module's own
// tasks (build-logic ModuleChecks.kt), so the root reads no other project. tallyChecks groups a module's checks,
// and detekt (verify.sh and CI) runs it for every module by task path. check_build_guards.py keeps this list equal to
// the modules in settings.gradle.kts. Part B3: checkJavaApiLevel too, in each JVM library module. Run: ./gradlew
// checkWarningsAsErrors checkJdkRelease checkJavaApiLevel (every module that has them).
val tallyModules = listOf(":app", ":core:data", ":core:domain", ":core:testing")
tasks.named("detekt") { dependsOn(tallyModules.map { "$it:tallyChecks" }) }

// M1-98: file trees, not "**/..." strings. For such a string Spotless excludes the root's and every subproject's build
// directory by reading that project's layout, which Gradle's isolated projects mode rejects; a file tree is used as given.
// The trees exclude the same: .git, .gradle, build/ and each module's build/ (scripts/test_spotless_gate.py).
fun spotlessFiles(
    vararg patterns: String,
    buildDirs: List<String>,
) = fileTree(rootDir) {
    include(*patterns)
    exclude(listOf(".git/**", ".gradle/**") + buildDirs)
}

val moduleBuildDirs = listOf("build/**") + tallyModules.map { it.removePrefix(":").replace(':', '/') + "/build/**" }

spotless {
    kotlin {
        target(spotlessFiles("**/src/**/*.kt", buildDirs = moduleBuildDirs))
        ktlint(libs.versions.ktlint.get())
    }
    kotlinGradle {
        target(spotlessFiles("*.gradle.kts", "**/*.gradle.kts", buildDirs = listOf("**/build/**")))
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
                classes( // justified: Hilt-generated code holds no hand-written logic
                    "dk.bjarkebjarke.tally.Hilt_*",
                    "dk.bjarkebjarke.tally.*_Factory",
                    "dk.bjarkebjarke.tally.*_GeneratedInjector",
                    "hilt_aggregated_deps.*",
                    "dagger.hilt.internal.aggregatedroot.codegen.*",
                )
                // Owner decisions 7127528405, 7129260438: what Dagger generates, its factories' nested holders too.
                annotatedBy("dagger.internal.DaggerGenerated") // justified: generated by Dagger, no hand-written logic
                classes("dk.bjarkebjarke.tally.*Factory\$InstanceHolder") // justified: generated by Dagger, no marker
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

// M0.5-10: the licensee policy (config/licensee/policy.gradle) is tested against a fixture build whose
// artifacts have chosen licences. Each case runs the fixture's `licensee` task: it must pass for the owner's
// allowlist and fail, naming the artifact, for any other licence. Wired into detekt, so verify.sh and CI run it.
// A case is one string, "name|deps|approved|pass or fail|text the output must contain|licensee version or empty", so the
// task stays configuration-cache friendly (no script object references).
fun licenseeCase(
    name: String,
    deps: String,
    approved: String = "",
    passes: Boolean,
    message: String = "",
    licensee: String = "",
) = listOf(name, deps, approved, if (passes) "pass" else "fail", message, licensee).joinToString("|")

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
        val realList = "../google-sdk-terms.txt"
        val m1o14Artifacts =
            listOf(
                "com.google.firebase:firebase-auth:25.0.0",
                "com.google.firebase:firebase-auth-interop:20.0.0",
                "com.google.android.gms:play-services-auth:21.1.1",
                "com.google.android.gms:play-services-auth-api-phone:18.0.2",
                "com.google.android.gms:play-services-auth-base:18.0.10",
                "com.google.android.gms:play-services-auth-blockstore:16.4.0",
                "com.google.android.gms:play-services-base:18.9.0",
                "com.google.android.gms:play-services-basement:18.9.0",
                "com.google.android.gms:play-services-fido:21.0.0",
                "com.google.android.gms:play-services-identity-credentials:16.0.0-alpha08",
                "com.google.android.gms:play-services-tasks:18.4.0",
                "com.google.android.libraries.identity.googleid:googleid:1.2.1",
                "com.google.android.recaptcha:recaptcha:18.6.1",
                "com.google.android.play:core-common:2.0.3",
                "com.google.android.play:integrity:1.3.0",
                "com.google.re2j:re2j:1.6",
                "org.codehaus.mojo:animal-sniffer-annotations:1.27",
            ).joinToString(",")
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
                // M1-26 (owner decisions, issue 15 comments 7083187223 and 7085175461): each Play terms URL is allowed for
                // exactly its own artifact (integrity: Play Integrity terms; core-common: Play Core license), listed.
                licenseeCase(
                    "play integrity terms on integrity, listed",
                    "com.google.android.play:integrity:1.0",
                    "approved-play-integrity.txt",
                    passes = true,
                ),
                licenseeCase(
                    "play core license on core-common, listed",
                    "com.google.android.play:core-common:1.0",
                    "approved-play-core-common.txt",
                    passes = true,
                ),
                licenseeCase(
                    "play integrity terms on integrity, not listed",
                    "com.google.android.play:integrity:1.0",
                    passes = false,
                    message = "integrity/overview#tos",
                ),
                // M1-O14 (owner decisions, issue 15 comments 7085175461 and 7095943127): the 17 artifacts :app needs for Firebase
                // Auth and Credential Manager, as fixture stubs with the real licence URLs, against the real google-sdk-terms.txt.
                licenseeCase(
                    "M1-O14: all 17 artifacts pass with the real list",
                    m1o14Artifacts,
                    realList,
                    passes = true,
                ),
                licenseeCase(
                    "M1-O14: Go licence URL on re2j",
                    "com.google.re2j:re2j:1.6",
                    passes = true,
                ),
                licenseeCase(
                    "M1-O14: MIT.txt URL on animal-sniffer-annotations",
                    "org.codehaus.mojo:animal-sniffer-annotations:1.27",
                    passes = true,
                ),
                licenseeCase(
                    "M1-O14: another Google SDK terms artifact still fails with the real list",
                    "com.google.firebase:firebase-database:21.0.0",
                    realList,
                    passes = false,
                    message = terms,
                ),
                licenseeCase(
                    "M1-O14: a listed artifact at another version still fails with the real list",
                    "com.google.firebase:firebase-auth:99.0.0",
                    realList,
                    passes = false,
                    message = terms,
                ),
                licenseeCase(
                    "M1-O14: Play Core license on core-common at an unlisted version still fails",
                    "com.google.android.play:core-common:2.0.9",
                    realList,
                    passes = false,
                    message = "playcore/license",
                ),
                licenseeCase(
                    "play integrity terms on another artifact, listed",
                    "fixture:play-tos:1.0",
                    "approved-play-tos.txt",
                    passes = false,
                    message = notGoogle,
                ),
                licenseeCase(
                    "play core license on another artifact, listed",
                    "fixture:play-core:1.0",
                    "approved-play-core.txt",
                    passes = false,
                    message = notGoogle,
                ),
                licenseeCase(
                    "play integrity terms on core-common, listed",
                    "com.google.android.play:core-common:2.0",
                    "approved-core-common-tos.txt",
                    passes = false,
                    message = notGoogle,
                ),
                licenseeCase(
                    "play core license on integrity, listed",
                    "com.google.android.play:integrity:2.0",
                    "approved-integrity-core.txt",
                    passes = false,
                    message = notGoogle,
                ),
                licenseeCase(
                    "unlisted google url, listed artifact",
                    "fixture:play-other:1.0",
                    "approved-play-other.txt",
                    passes = false,
                    message = notGoogle,
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
                // Issue 217 item 4: the fixture build verifies dependencies (config/licensee/fixture/gradle). An older licensee
                // version that is on Maven Central but not in that file must be refused by Gradle, whatever its licences. The expected
                // text appears only when strict verification stops the plugin from resolving; lenient mode prints the same warning,
                // resolves the plugin and fails later for another reason.
                licenseeCase(
                    "dependency verification is on in the fixture build",
                    allowed,
                    passes = false,
                    message =
                        "Error resolving plugin [id: 'app.cash.licensee', version: '1.0.0']\n" +
                            "> Dependency verification failed",
                    licensee = "1.0.0",
                ),
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
                val fields = line.split('|')
                val (name, deps, approved, expected, message) = fields
                val licensee = fields[5]
                val passes = expected == "pass"
                val command =
                    mutableListOf(
                        wrapper.path,
                        "-q",
                        "--console=plain",
                        "--no-daemon",
                        "-p",
                        fixture.path,
                        "-Dlicensee.version=${licensee.ifEmpty { pluginVersion }}",
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
tasks.named("detekt") {
    dependsOn(testLicenseeGate, testDetektRules, ":app:licensee", ":core:data:licensee", ":core:domain:licensee")
}

// M1-05: CI's unit job calls koverVerify, so PIT on core/domain rides along without a separate workflow step.
tasks.named("koverVerify") { dependsOn(":core:domain:pitest") }
