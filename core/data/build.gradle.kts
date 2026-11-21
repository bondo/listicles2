plugins {
    alias(libs.plugins.android.library)
}

// M0.5-10: no licensee gate here yet. Nothing ships from this module until :app depends on it (M1-14); that PR applies
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
    compileSdk = 37

    defaultConfig {
        minSdk = 26
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // The emulator tests restore the project's Firestore rules after a test that loads its own, so the rules file travels
    // in the test APK's assets (read by FirebaseEmulator). Synced from firebase/, never copied by hand.
    sourceSets.getByName("androidTest").assets.srcDir(firestoreRulesAssetDir.get().asFile)
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        allWarningsAsErrors.set(true)
    }
}

dependencies {
    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.auth)
    implementation(libs.firebase.firestore)

    // #217 item 3: the shared test-JVM network block applies to this module's JVM unit tests too.
    testImplementation(project(":core:testing"))

    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.androidx.test.runner)
}
