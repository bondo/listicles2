plugins {
    alias(libs.plugins.listicles.android.library)
}

// M0.5-10: no licensee gate here yet. Nothing ships from this module until :app depends on it (M1-66); that PR applies
// config/licensee/policy.gradle, and the owner approves the Google SDK terms lines for the Firebase artifacts there.

val firestoreRulesAssetDir = layout.buildDirectory.dir("generated/firestoreRules")
val syncFirestoreRulesAsset =
    tasks.register<Sync>("syncFirestoreRulesAsset") {
        from(rootProject.file("firebase/firestore.rules"))
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
    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.auth)
    implementation(libs.firebase.firestore)

    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.androidx.test.runner)
}
