plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.hivision.idphotos"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.hivision.idphotos"
        minSdk = 26
        targetSdk = 34
        versionCode = 4
        versionName = "1.3-性能与稳定"
        ndk {
            abiFilters += "arm64-v8a"   // 真机全是 arm64，减小 APK 体积
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    androidResources {
        // 224MB 模型不压缩，避免运行时解压开销
        noCompress.add("onnx")
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-ktx:1.9.0")
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.18.0")
}
