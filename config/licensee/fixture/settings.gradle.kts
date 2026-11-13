// Fixture build for the licensee gate (:testLicenseeGate in the root build). Not part of the app build.
// It applies the real policy (../policy.gradle.kts) to local POM-only artifacts with chosen licences.
pluginManagement {
    repositories {
        maven("https://maven-central.storage-download.googleapis.com/maven2")
        mavenCentral()
    }
    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == "app.cash.licensee") {
                useVersion(System.getProperty("licensee.version"))
            }
        }
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        maven(uri("repo")) { name = "FixtureRepo" }
    }
}

rootProject.name = "licensee-fixture"
