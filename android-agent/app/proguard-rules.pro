# Add project specific ProGuard rules here.
# By default, the flags in this file are appended to flags specified
# in proguard-android-optimize.txt.

# Keep build config.
-keep class com.aegisone.agent.BuildConfig { *; }

# Kotlin Serialization.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keep,includedescriptorclasses class com.aegisone.agent.**$$serializer { *; }
-keepclassmembers class com.aegisone.agent.** {
    *** Companion;
}
-keepclasseswithmembers class com.aegisone.agent.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# Retrofit + OkHttp.
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn retrofit2.**
-keep,allowobfuscation,allowshrinking interface retrofit2.Call
-keep,allowobfuscation,allowshrinking class retrofit2.Response

# Hilt / Dagger.
-dontwarn com.google.errorprone.annotations.**