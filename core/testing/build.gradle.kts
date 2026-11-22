plugins {
    alias(libs.plugins.listicles.jvm.testsupport)
}

dependencies {
    // M1-30: FakeConnectivity implements the domain's Connectivity.
    api(project(":core:domain"))
    implementation(platform(libs.junit.bom))
    implementation(libs.junit.platform.launcher)

    testImplementation(libs.junit.jupiter)
    testImplementation(libs.kotest.assertions)
    testRuntimeOnly(libs.junit.platform.launcher)
}

tasks.test {
    useJUnitPlatform()
    failOnNoDiscoveredTests = true
}
