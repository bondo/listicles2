// Maven Central's own host answers a share of requests from shared cloud IPs with HTTP 429, and Gradle
// disables a repository for the whole build once one request runs out of retries. So artifacts come from
// Google's mirror of Maven Central first, and google() is asked only for the groups it hosts.
// mavenCentral() is used only for artifacts the mirror does not have (a 404 there). If the mirror itself
// keeps failing until its retries run out, the build fails; it does not fall through to mavenCentral().
// Checked by scripts/check_gradle_repos.py.
pluginManagement {
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
    }
}

rootProject.name = "listicles"

include(":app", ":core:domain")
