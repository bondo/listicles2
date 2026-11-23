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
            id = "listicles.jvm.library"
            implementationClass = "JvmLibraryConventionPlugin"
        }
        register("jvmTestSupport") {
            id = "listicles.jvm.testsupport"
            implementationClass = "JvmTestSupportConventionPlugin"
        }
        register("androidLibrary") {
            id = "listicles.android.library"
            implementationClass = "AndroidLibraryConventionPlugin"
        }
        register("androidApplication") {
            id = "listicles.android.application"
            implementationClass = "AndroidApplicationConventionPlugin"
        }
        register("dependencyFloors") {
            id = "listicles.dependency.floors"
            implementationClass = "DependencyFloorsPlugin"
        }
    }
}
