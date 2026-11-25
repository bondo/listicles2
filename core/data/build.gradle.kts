plugins {
    alias(libs.plugins.listicles.android.library)
    alias(libs.plugins.licensee)
}

// M0.5-10, M1-66: :app ships this module, so its dependencies must be on the owner's licence allowlist too
// (the Google SDK terms lines in config/licensee/google-sdk-terms.txt, approved in M1-O14).
apply(
    from =
        isolated.rootProject.projectDirectory
            .file("config/licensee/policy.gradle")
            .asFile,
)

val firestoreRulesAssetDir = layout.buildDirectory.dir("generated/firestoreRules")
val syncFirestoreRulesAsset =
    tasks.register<Sync>("syncFirestoreRulesAsset") {
        from(isolated.rootProject.projectDirectory.file("firebase/firestore.rules"))
        into(firestoreRulesAssetDir)
    }

// A directory handed to the Android SourceSet API carries no task dependency, so every task that reads the test assets says so.
tasks.configureEach {
    if (name.contains("AndroidTest")) dependsOn(syncFirestoreRulesAsset)
}

android {
    namespace = "dk.bjarkebjarke.tally.data"

    // The tests restore the project's Firestore rules (FirebaseEmulator): they travel in the test APK's assets, synced from firebase/.
    sourceSets.getByName("androidTest").assets.srcDir(firestoreRulesAssetDir.get().asFile)
}

dependencies {
    // M1-67: implements the domain's session interfaces (M1-14) over Firebase; its public classes expose them.
    api(project(":core:domain"))
    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.auth)
    implementation(libs.firebase.firestore)
    implementation(libs.kotlinx.coroutines.play.services)
    // M1-66: GoogleCredentials over Credential Manager with Sign in with Google. :app passes a CredentialManager in, and
    // on Android 13 and below that CredentialManager needs the Play services provider (lint CredentialDependency).
    api(libs.androidx.credentials)
    api(libs.androidx.credentials.play.services.auth)
    implementation(libs.googleid)

    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.androidx.test.runner)
}
