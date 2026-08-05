-dontobfuscate

### Don't remove subsonic api serializers/entities
-keep class nl.teunschriks.mumamobile.api.subsonic.** { *; }
-keep class nl.teunschriks.mumamobile.api.muma.** { *; }

## Don't remove the domain models
-keep class nl.teunschriks.mumamobile.domain.** { *; }

## Don't remove the imageloader
-keep class nl.teunschriks.mumamobile.imageloader.** { *; }
-keep class nl.teunschriks.mumamobile.provider.AlbumArtContentProvider { *; }

## Don't remove NowPlayingFragment
-keep class nl.teunschriks.mumamobile.fragment.NowPlayingFragment { *; }

## Guava's TypeToken resolves its type argument from the generic superclass of an anonymous
## subclass at runtime. Unlike Gson, Guava ships no consumer rules, so with
## android.enableR8.fullMode=true R8 merges that superclass away and TypeCapture.capture()
## throws "class com.google.common.reflect.TypeCapture isn't parameterized" in release builds.
## Keep the hierarchy and its signatures so any remaining/new usage keeps working.
-keepattributes Signature, InnerClasses, EnclosingMethod
-keep class com.google.common.reflect.TypeToken
-keep class * extends com.google.common.reflect.TypeToken
