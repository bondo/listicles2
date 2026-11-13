plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kover)
    alias(libs.plugins.detekt)
    alias(libs.plugins.licensee)
}

// M0.5-10: shipped dependencies must be on the owner's licence allowlist.
apply(from = rootProject.file("config/licensee/policy.gradle"))

detekt {
    // Type-resolved tasks (detektMain, detektTest); the root task covers all sources without types.
    buildUponDefaultConfig = true
    config.setFrom(rootProject.file("config/detekt/detekt.yml"))
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        allWarningsAsErrors.set(true)
    }
}

dependencies {
    testImplementation(platform(libs.junit.bom))
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.kotest.runner)
    testImplementation(libs.kotest.assertions)
    testImplementation(libs.kotest.property)
    testImplementation(libs.konsist)
    testImplementation(project(":core:testing"))
    testRuntimeOnly(libs.junit.platform.launcher)
}

tasks.test {
    useJUnitPlatform()
    // A test task that runs zero tests is a failure, not a pass.
    failOnNoDiscoveredTests = true
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
