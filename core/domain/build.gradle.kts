plugins {
    alias(libs.plugins.tally.jvm.library)
    alias(libs.plugins.kover)
    alias(libs.plugins.licensee)
    alias(libs.plugins.pitest)
}

// M0.5-10: shipped dependencies must be on the owner's licence allowlist.
apply(
    from =
        isolated.rootProject.projectDirectory
            .file("config/licensee/policy.gradle")
            .asFile,
)

dependencies {
    // M1-60: observable state (Flow) in domain interfaces, e.g. SessionState (checklist section 4).
    api(libs.kotlinx.coroutines.core)
    testImplementation(platform(libs.junit.bom))
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.kotest.runner)
    testImplementation(libs.kotest.assertions)
    testImplementation(libs.kotest.property)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.konsist)
    testRuntimeOnly(libs.junit.platform.launcher)
}

tasks.test {
    // The shared test-JVM network block has its own tests; running the domain tests runs them too.
    dependsOn(":core:testing:test")
}

kover {
    reports {
        verify {
            rule("domain line coverage") {
                minBound(95)
            }
            rule("domain branch coverage") {
                minBound(90, kotlinx.kover.gradle.plugin.dsl.CoverageUnit.BRANCH)
            }
        }
    }
}

// M1-05 (PLAN P16): mutation testing so tests without real assertions cannot satisfy the coverage gate.
// The floor is 80 (owner decision, issue 15): raise it later, never lower it (scripts/check_pit_config.py).
pitest {
    pitestVersion.set(libs.versions.pitest.get())
    junit5PluginVersion.set("1.2.3")
    targetClasses.set(listOf("dk.bjarkebjarke.tally.domain.*"))
    targetTests.set(listOf("dk.bjarkebjarke.tally.domain.*"))
    // PIT defaults without VOID_METHOD_CALLS: Kotlin's generated null checks (Intrinsics.checkNotNull*) are equivalent mutants no test
    // can kill, and avoidCallsTo would drop every mutant on a line that calls them. Conditionals, returns and arithmetic stay mutated.
    mutators.set(
        listOf(
            "CONDITIONALS_BOUNDARY",
            "INCREMENTS",
            "INVERT_NEGS",
            "MATH",
            "NEGATE_CONDITIONALS",
            "EMPTY_RETURNS",
            "FALSE_RETURNS",
            "TRUE_RETURNS",
            "NULL_RETURNS",
            "PRIMITIVE_RETURNS",
        ),
    )
    mutationThreshold.set(80)
    outputFormats.set(listOf("XML", "HTML"))
    timestampedReports.set(false)
}
