// M1-46 (issues 217 and 48): the convention plugins every module applies instead of root allprojects/subprojects blocks.
// Same repository order as the root settings.gradle.kts (Google's Maven Central mirror first; see the comment there).
pluginManagement {
    repositories {
        maven("https://maven-central.storage-download.googleapis.com/maven2") { name = "MavenCentralMirror" }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google {
            content {
                includeGroupAndSubgroups("androidx")
                includeGroupAndSubgroups("com.android")
                includeGroupAndSubgroups("com.google")
            }
        }
        maven("https://maven-central.storage-download.googleapis.com/maven2") { name = "MavenCentralMirror" }
        mavenCentral()
        gradlePluginPortal()
    }
    // The root build's catalog, so build-logic compiles against the plugin versions the build applies.
    val rootCatalog = files("../gradle/libs.versions.toml")
    versionCatalogs.create("libs") { from(rootCatalog) } // justified: an included build loads the root catalog file
}

rootProject.name = "build-logic"
