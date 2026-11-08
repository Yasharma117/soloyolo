plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "dev.soloyolo.listener"
    compileSdk = 35

    defaultConfig {
        applicationId = "dev.soloyolo.listener"
        minSdk = 28          // MessagingStyle Person, EXTRA_IS_GROUP_CONVERSATION
        targetSdk = 35
        versionCode = 1
        versionName = "0.1"
    }
    buildTypes {
        release { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")      // NotificationCompat.MessagingStyle.extract...
    implementation("androidx.work:work-runtime-ktx:2.9.1") // upload when there's a network, survives Doze
    testImplementation("junit:junit:4.13.2")
}
