import org.gradle.api.Project
import org.gradle.api.artifacts.ProjectDependency
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.kotlin.dsl.withType
import org.jetbrains.kotlin.gradle.tasks.KotlinCompilationTask

// M1-68 part B2 (issue 48): every module checks its own compile tasks and configurations, so the root reads no other
// project. listiclesChecks groups a module's checks; the root build names `<module>:listiclesChecks` by task path for
// each module in its listiclesModules (check_build_guards.py keeps that list equal to settings.gradle.kts).
// Tested by scripts/test_warnings_gate.py and scripts/test_jdk_release_gate.py.

private const val JDK_RELEASE = "17"
private const val WARNINGS =
    "warnings are not all errors (allWarningsAsErrors off, suppressWarnings, -nowarn, " +
        "-Xsuppress-warning, -Xwarning-level=...:disabled/warning/info) for: "

/** Registers checkWarningsAsErrors, checkJdkRelease and listiclesChecks; [jdkRelease]: the JDK 17 API applies. */
internal fun Project.registerModuleChecks(
    jdkRelease: Boolean,
    testSupport: String,
) {
    val warnings = registerWarningsCheck()
    val release = registerJdkReleaseCheck(jdkRelease, testSupport)
    tasks.register("listiclesChecks") {
        group = "verification"
        description = "Runs this module's own checks (the root's detekt runs it for every module)."
        dependsOn(warnings, release, "checkTestSettings")
    }
}

/**
 * Flags that turn warnings off or hide them, which would bypass allWarningsAsErrors (M0.5-09). A bare flag takes
 * the next element as its value, so the list is read as a sequence; every entry of a comma-separated value must
 * raise its diagnostic to an error.
 */
internal fun hidesWarnings(args: List<String>): Boolean =
    args.withIndex().any { (i, arg) ->
        val value = if (arg.contains('=')) arg.substringAfter('=') else args.getOrNull(i + 1).orEmpty()
        val entries = value.split(',').map { it.trim() }.filter { it.isNotEmpty() }
        val allErrors = entries.isNotEmpty() && entries.all { it.endsWith(":error") }
        arg == "-nowarn" || arg.startsWith("-Xsuppress-warning") || (arg.startsWith("-Xwarning-level") && !allErrors)
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
    testSupport: String,
) = tasks.register("checkJdkRelease") {
    group = "verification"
    description = "Fails if this module's compile tasks or non-test configurations can reach the JDK 21 API."
    val p = project
    val leaks =
        p.provider {
            p.configurations.filterNot { it.name.contains("test", ignoreCase = true) }.flatMap { c ->
                c.dependencies
                    .withType<ProjectDependency>()
                    .filter { it.path == testSupport }
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
