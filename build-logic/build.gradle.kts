plugins {
    `kotlin-dsl`
}

kotlin {
    compilerOptions { allWarningsAsErrors.set(true) }
}

dependencies {
    compileOnly(libs.android.gradle.api)
    compileOnly(libs.kotlin.gradle.plugin)
    compileOnly(libs.detekt.gradle.plugin)
}

gradlePlugin {
    plugins {
        register("jvmLibrary") {
            id = "tally.jvm.library"
            implementationClass = "JvmLibraryConventionPlugin"
        }
        register("jvmTestSupport") {
            id = "tally.jvm.testsupport"
            implementationClass = "JvmTestSupportConventionPlugin"
        }
        register("androidLibrary") {
            id = "tally.android.library"
            implementationClass = "AndroidLibraryConventionPlugin"
        }
        register("androidApplication") {
            id = "tally.android.application"
            implementationClass = "AndroidApplicationConventionPlugin"
        }
        register("dependencyFloors") {
            id = "tally.dependency.floors"
            implementationClass = "DependencyFloorsPlugin"
        }
    }
}
