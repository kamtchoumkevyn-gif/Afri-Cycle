# R8 shrinks the release build. Activities, services and providers named in
# AndroidManifest.xml are kept automatically, and the libraries bring their own rules.
# The built-in screen (WebAppActivity) gives pages no Java objects to call, so there is
# no @JavascriptInterface to keep.

# Readable stack traces in crash reports
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile
