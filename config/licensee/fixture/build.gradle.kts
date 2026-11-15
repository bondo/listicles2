// -Pdeps=group:artifact:version,...  the artifacts to resolve (all under repo/)
// -Papproved=file                    optional Google/Android SDK terms list, relative to this directory
plugins {
    `java-library`
    id("app.cash.licensee")
}

// The Google/Android SDK terms list the policy reads. Without -Papproved it is empty.
extra["licenseeGoogleTermsFile"] = file(providers.gradleProperty("approved").getOrElse("none.txt"))
apply(from = "../policy.gradle")

dependencies {
    providers
        .gradleProperty("deps")
        .getOrElse("")
        .split(',')
        .filter { it.isNotBlank() }
        .forEach { implementation(it) }
}
