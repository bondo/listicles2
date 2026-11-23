// Fixture build for the licensee gate (:testLicenseeGate in the root build). Not part of the app build.
// It applies the real policy (../policy.gradle) to local POM-only artifacts with chosen licences.
// Dependency verification (issue 217 item 4): gradle/verification-metadata.xml here covers the remote artifacts only (the licensee
// plugin and its dependencies); Gradle does not verify the local repo/ POMs. A licensee bump in the root catalog needs it regenerated:
//   rm -r gradle; ../../../gradlew --no-configuration-cache --refresh-dependencies --write-verification-metadata sha256 \
//     -Dlicensee.version=<catalog version> -Pdeps=fixture:mit:1.0 licensee
// then delete the group="fixture" components Gradle writes for repo/. scripts/check_gradle_repos.py checks the file and the version.
// pluginManagement lists the mirror and mavenCentral() as the root settings do; dependencies come from repo/ only, so the
// mirror-first rule applies to pluginManagement alone.
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
