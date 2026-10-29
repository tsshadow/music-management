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

## Gson reads these back from SharedPreferences and has to know their field names and, where a
## field is a collection, its element type. With android.enableR8.fullMode=true R8 strips the
## generic signature of any class it was not told to keep, and Gson then hands back LinkedTreeMap
## instead of the model -- which is a ClassCastException at the point something draws it, not at
## the point it is parsed. That shipped in 6.21.0 and crashed the home screen on startup.
##
## CardListCache no longer depends on this (it passes an explicit TypeToken), but every other
## stored model still does, and the next one added will too.
-keep class nl.teunschriks.mumamobile.home.HomeCard { *; }
-keep class nl.teunschriks.mumamobile.home.HomeCardType { *; }
