## Capacitor finds everything by reflection: the bridge looks plugins up by the name in
## @CapacitorPlugin, and a call from JavaScript is dispatched to a @PluginMethod by its method
## name. R8 has no way to see any of that, and with android.enableR8.fullMode=true it removes
## the methods and rewrites the names, which shows up at runtime as "MumaPlayer does not have a
## method called setQueue" rather than as a build failure.

-keep class com.getcapacitor.** { *; }
-keep interface com.getcapacitor.** { *; }

-keep @com.getcapacitor.annotation.CapacitorPlugin public class * extends com.getcapacitor.Plugin {
    @com.getcapacitor.annotation.PermissionCallback <methods>;
    @com.getcapacitor.annotation.ActivityCallback <methods>;
    @com.getcapacitor.annotation.Permission <methods>;
    @com.getcapacitor.PluginMethod public <methods>;
}

## Our own plugins, whole: the class names above are what the WebView asks for by string.
-keep class nl.teunschriks.mumamobile.capacitor.** { *; }

## Cordova ships inside capacitor core for plugin compatibility. Nothing here uses a Cordova
## plugin, but the bridge still initialises the framework, which reflects over these.
-keep class org.apache.cordova.** { *; }
-dontwarn org.apache.cordova.**
