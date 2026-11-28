import com.android.build.api.variant.ApplicationAndroidComponentsExtension
import org.gradle.api.Project
import org.gradle.api.artifacts.ProjectDependency
import org.gradle.api.attributes.Usage
import org.gradle.api.tasks.Exec
import org.gradle.api.tasks.SourceSetContainer
import org.gradle.api.tasks.TaskProvider
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.kotlin.dsl.getByType
import org.gradle.kotlin.dsl.named
import org.gradle.kotlin.dsl.property
import org.gradle.kotlin.dsl.register
import org.gradle.kotlin.dsl.withType
import org.gradle.process.CommandLineArgumentProvider
import org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask

// M1-68 part B2 (issue 48): every module checks its own compile tasks and configurations, so the root reads no other
// project. tallyChecks groups a module's checks; the root build names `<module>:tallyChecks` by task path for
// each module in its tallyModules (check_build_guards.py keeps that list equal to settings.gradle.kts).
// Tested by scripts/test_warnings_gate.py, scripts/test_jdk_release_gate.py and scripts/test_java_api_level_gate.py.

private const val JDK_RELEASE = "17"
private const val WARNINGS =
    "warnings are not all errors (allWarningsAsErrors off, suppressWarnings, -nowarn, -Xsuppress-*, -Xdont-warn*, " +
        "an @argfile, -Xwarning-level=...:disabled/warning/info) for: "

// M1-68 part B3: the app hands its minSdk and api-versions.xml to the JVM modules' checkJavaApiLevel as an artifact
// with this Usage, which no other variant has. A dependency on the app, not a read of its configuration.
private const val JAVA_API_LEVEL = "tally-java-api-level"
private const val APP = ":app"

/** Registers checkWarningsAsErrors, checkJdkRelease and tallyChecks; [jdkRelease]: the JDK 17 API applies. */
internal fun Project.registerModuleChecks(
    jdkRelease: Boolean,
    testSupport: Set<String>,
) {
    val warnings = registerWarningsCheck()
    val release = registerJdkReleaseCheck(jdkRelease, testSupport)
    // A JVM module that may reach the app; lint's NewApi covers the Android modules, and test support never ships.
    val apiLevel = if (jdkRelease) listOf(registerJavaApiLevelCheck()) else emptyList()
    tasks.register("tallyChecks") {
        group = "verification"
        description = "Runs this module's own checks (the root's detekt runs it for every module)."
        dependsOn(warnings, release, "checkTestSettings", apiLevel)
    }
}

/**
 * Flags that turn warnings off or hide them, which would bypass allWarningsAsErrors (M0.5-09). A bare flag takes
 * the next element as its value, so the list is read as a sequence; every entry of a comma-separated value must
 * raise its diagnostic to an error. Issue 48: every -Xsuppress-* and -Xdont-warn* flag, and any @argfile (its
 * contents are not checked here), counts too.
 */
internal fun hidesWarnings(args: List<String>): Boolean =
    args.withIndex().any { (i, arg) ->
        val value = if (arg.contains('=')) arg.substringAfter('=') else args.getOrNull(i + 1).orEmpty()
        val entries = value.split(',').map { it.trim() }.filter { it.isNotEmpty() }
        val allErrors = entries.isNotEmpty() && entries.all { it.endsWith(":error") }
        arg == "-nowarn" || arg.startsWith("@") || arg.startsWith("-Xsuppress-") || arg.startsWith("-Xdont-warn") ||
            (arg.startsWith("-Xwarning-level") && !allErrors)
    }

/** M0.5-09: every Kotlin compile task of this module (all variants, tests included) treats warnings as errors. */
private fun Project.registerWarningsCheck() =
    tasks.register("checkWarningsAsErrors") {
        group = "verification"
        description = "Fails if a Kotlin compile task here does not set allWarningsAsErrors or hides warnings."
        // Evaluated when the task graph is built, after the module (and any later block) has configured its tasks.
        val compiles = project.tasks.withType<KotlinCompilationTask<*>>()
        val taskCount = project.provider { compiles.size }
        val offenders =
            project.provider {
                compiles
                    .filter {
                        val o = it.compilerOptions
                        !o.allWarningsAsErrors.getOrElse(false) ||
                            o.suppressWarnings.getOrElse(false) ||
                            hidesWarnings(o.freeCompilerArgs.getOrElse(emptyList()))
                    }.map { it.path }
            }
        inputs.property("taskCount", taskCount)
        inputs.property("offenders", offenders)
        doLast {
            check(taskCount.get() > 0) { "checkWarningsAsErrors found no Kotlin compile tasks; the check is broken" }
            check(offenders.get().isEmpty()) { WARNINGS + offenders.get().joinToString() }
        }
    }

/** The last -Xjdk-release value wins, as on the Kotlin command line; a bare flag has no value. */
internal fun kotlinReleaseOk(args: List<String>) =
    args.lastOrNull { it.startsWith("-Xjdk-release") }?.substringAfter('=', "") == JDK_RELEASE

internal fun javaReleaseOk(release: String) = release == JDK_RELEASE

/** Negative cases first: a predicate that accepts everything would make the real check pass. */
internal fun jdkReleaseSelfTest() =
    listOf(
        kotlinReleaseOk(listOf("-Xjdk-release=17")),
        kotlinReleaseOk(listOf("-Xfoo", "-Xjdk-release=17", "-Xbar")),
        !kotlinReleaseOk(emptyList()),
        !kotlinReleaseOk(listOf("-Xjdk-release=21")),
        !kotlinReleaseOk(listOf("-Xjdk-release=1.8")),
        !kotlinReleaseOk(listOf("-Xjdk-release=17", "-Xjdk-release=21")),
        !kotlinReleaseOk(listOf("-Xjdk-release")),
        !kotlinReleaseOk(listOf("-Xjdk-release=")),
        !kotlinReleaseOk(listOf("-Xjdk-release=170")),
        javaReleaseOk("17"),
        !javaReleaseOk(""),
        !javaReleaseOk("21"),
        !javaReleaseOk("1.8"),
    )

/**
 * Issue 211: a JVM library compiles against the JDK 17 API (Kotlin -Xjdk-release and Java --release), not the JDK 21
 * one the build runs on; minSdk is 26 and Android has List.removeFirst()/removeLast() only from API 35. This closes the
 * JDK 18 to 21 gap only (checkJavaApiLevel checks Java 9 to 17 APIs newer than API 26). In every module, no non-test
 * configuration may depend on the test-support module, which uses the JDK 21 API on purpose.
 */
private fun Project.registerJdkReleaseCheck(
    jdkRelease: Boolean,
    testSupport: Set<String>,
) = tasks.register("checkJdkRelease") {
    group = "verification"
    description = "Fails if this module's compile tasks or non-test configurations can reach the JDK 21 API."
    val p = project
    val leaks =
        p.provider {
            p.configurations.filterNot { it.name.contains("test", ignoreCase = true) }.flatMap { c ->
                c.dependencies
                    .withType<ProjectDependency>()
                    .filter { it.path in testSupport }
                    .map { "${p.path}:${c.name} -> ${it.path}" }
            }
        }
    val kotlinTasks =
        p.provider {
            if (!jdkRelease) return@provider emptyList()
            p.tasks.withType<KotlinCompilationTask<*>>().map {
                it.path to it.compilerOptions.freeCompilerArgs.getOrElse(emptyList())
            }
        }
    val javaTasks =
        p.provider {
            if (!jdkRelease) return@provider emptyList()
            p.tasks.withType<JavaCompile>().map {
                it.path to
                    it.options.release
                        .map { r -> "$r" }
                        .getOrElse("")
            }
        }
    inputs.property("leaks", leaks)
    inputs.property("kotlinTasks", kotlinTasks)
    inputs.property("javaTasks", javaTasks)
    doLast {
        val selfTest = jdkReleaseSelfTest()
        check(selfTest.all { it }) { "checkJdkRelease self-test failed: $selfTest" }
        check(!jdkRelease || (kotlinTasks.get().isNotEmpty() && javaTasks.get().isNotEmpty())) {
            "checkJdkRelease found no JVM module compile tasks; the check is broken"
        }
        check(leaks.get().isEmpty()) {
            "test-support modules (use JDK 21 API) must only be test dependencies: ${leaks.get().joinToString()}"
        }
        val offenders =
            kotlinTasks.get().filterNot { (_, args) -> kotlinReleaseOk(args) }.map { (path, args) ->
                val flags = args.filter { it.startsWith("-Xjdk-release") }.ifEmpty { listOf("no -Xjdk-release") }
                "$path (Kotlin: $flags)"
            } +
                javaTasks.get().filterNot { (_, release) -> javaReleaseOk(release) }.map { (path, release) ->
                    "$path (Java release: ${release.ifEmpty { "unset" }})"
                }
        check(offenders.isEmpty()) {
            "JVM modules must compile against the JDK $JDK_RELEASE API (-Xjdk-release=$JDK_RELEASE, " +
                "options.release=$JDK_RELEASE), not the JDK 21 one the build runs on: Android has the JDK 18 to 21 " +
                "API (for example List.removeFirst) only from API 35 and minSdk is 26. " +
                "Offenders: ${offenders.joinToString()}"
        }
    }
}

/**
 * M1-37 (issue 228): checkJdkRelease closes the JDK 18 to 21 gap only. A Java 9 to 17 member that is newer than minSdk
 * (Stream.toList is API 34, Objects.requireNonNullElse is API 30) still compiles in a JVM module, and Android lint's
 * NewApi skips pure JVM modules. This runs scripts/check_java_api_level.py over the module's main classes against the
 * api-versions.xml of the app's compileSdk platform, with the app's minSdk: both come from the app
 * (registerJavaApiLevelInputs) through a dependency, so they cannot drift from it. A missing or unreadable
 * api-versions.xml fails the build.
 */
private fun Project.registerJavaApiLevelCheck(): TaskProvider<Exec> {
    val declared = configurations.dependencyScope("tallyJavaApiLevel")
    val fromApp =
        configurations.resolvable("tallyJavaApiLevelFromApp") {
            extendsFrom(declared.get())
            attributes.attribute(Usage.USAGE_ATTRIBUTE, objects.named(JAVA_API_LEVEL))
        }
    dependencies.add(declared.name, dependencies.project(mapOf("path" to APP)))
    val appFiles = files(fromApp)
    val checker = isolated.rootProject.projectDirectory.file("scripts/check_java_api_level.py")
    val classDirs =
        extensions
            .getByType<SourceSetContainer>()
            .getByName("main")
            .output.classesDirs
    return tasks.register<Exec>("checkJavaApiLevel") {
        group = "verification"
        description = "Fails if this module's main classes use a java/ or android/ member above the app's minSdk."
        inputs.file(checker)
        inputs.files(classDirs).withPropertyName("classDirs")
        inputs.files(appFiles).withPropertyName("fromApp")
        executable = "python3"
        argumentProviders.add(
            CommandLineArgumentProvider {
                // Two lines from the app: its minSdk and the api-versions.xml path (missing file: the checker fails).
                val (minSdk, apiVersions) = appFiles.singleFile.readLines()
                listOf("-I", checker.asFile.path, "--api-versions", apiVersions, "--min-sdk", minSdk) +
                    classDirs.files.filter { it.exists() }.map { it.path }
            },
        )
    }
}

/** The app's side of checkJavaApiLevel: its debug minSdk and the api-versions.xml of its compileSdk platform. */
internal fun Project.registerJavaApiLevelInputs() {
    val components = extensions.getByType<ApplicationAndroidComponentsExtension>()
    val minSdk = objects.property<Int>()
    components.onVariants(components.selector().withName("debug")) { minSdk.set(it.minSdk.apiLevel) }
    // Resolving the boot classpath makes AGP install the compileSdk platform when it is missing.
    val apiVersions =
        components.sdkComponents.bootClasspath.map { jars ->
            jars
                .first { it.asFile.name == "android.jar" }
                .asFile
                .resolveSibling("data/api-versions.xml")
                .path
        }
    val output = layout.buildDirectory.file("tally/java-api-level.txt")
    val write =
        tasks.register("tallyJavaApiLevelInputs") {
            description = "Writes the app's minSdk and api-versions.xml path for the JVM modules' checkJavaApiLevel."
            inputs.property("minSdk", minSdk)
            inputs.property("apiVersions", apiVersions)
            outputs.file(output)
            doLast { output.get().asFile.writeText("${minSdk.get()}\n${apiVersions.get()}\n") }
        }
    configurations.consumable("tallyJavaApiLevelElements") {
        attributes.attribute(Usage.USAGE_ATTRIBUTE, objects.named(JAVA_API_LEVEL))
        outgoing.artifact(output) { builtBy(write) }
    }
}
