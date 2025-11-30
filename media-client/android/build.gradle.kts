allprojects {
    repositories {
        maven { url = uri("https://maven.aliyun.com/repository/google") }
        maven { url = uri("https://maven.aliyun.com/repository/public") }
        maven { url = uri("https://maven.aliyun.com/repository/gradle-plugin") }
        maven { url = uri("https://storage.flutter-io.cn/download.flutter.io") }
        maven { url = uri("https://storage.googleapis.com/download.flutter.io") }
        maven { url = uri("/home/meal/flutter/flutter/bin/cache/artifacts/engine/android-arm64") }
        maven { url = uri("/home/meal/flutter/flutter/bin/cache/artifacts/engine/android-arm") }
        maven { url = uri("/home/meal/flutter/flutter/bin/cache/artifacts/engine/android-x64") }
        maven { url = uri("/home/meal/flutter/flutter/bin/cache/artifacts/engine/android-x86") }
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
