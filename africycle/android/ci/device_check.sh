#!/usr/bin/env bash
# Installs Africycle on the running Android emulator and checks, like a person would, that
# it installs, opens and shows Africycle, then probes its security. Used by
# .github/workflows/android.yml on every Android version.
#
#   bash device_check.sh <app.apk> <results folder> <label, e.g. api24-google_apis>
#
# Writes <label>.txt (what happened), <label>.png (the screen) and <label>-logcat.txt.
# Exits 1 when the app doesn't install, crashes, shows nothing, or opens a foreign site.
set -u
APK=$1
OUT=$2
LABEL=$3
PKG=cm.africycle.app
mkdir -p "$OUT"
REPORT="$OUT/$LABEL.txt"
: > "$REPORT"
problems=()

say() { echo "$*" | tee -a "$REPORT"; }
shell() { adb shell "$@" 2>&1 | tr -d '\r'; }
problem() { problems+=("$1"); say "PROBLEM: $1"; }

API=$(shell getprop ro.build.version.sdk)
say "== Africycle on Android $(shell getprop ro.build.version.release) (API $API), $LABEL"
say "Chrome: $(shell dumpsys package com.android.chrome | grep -m1 versionName | sed 's/ *//')"
if [ "$API" -ge 24 ]; then
  say "WebView: $(shell dumpsys webviewupdate | grep -m1 -i 'current webview package' | sed 's/^ *//')"
else
  say "WebView: $(shell dumpsys package com.android.webview | grep -m1 versionName | sed 's/ *//')"
fi

# ---- 1. Install ----
installed=$(adb install -r "$APK" 2>&1 | tr -d '\r')
say "install: $installed"
if ! echo "$installed" | grep -q Success; then
  problem "the APK did not install"
fi

# Chrome without its first-run screens, as on a phone that has been set up
if shell pm path com.android.chrome | grep -q package:; then
  shell 'echo "chrome --disable-fre --no-default-browser-check --no-first-run" > /data/local/tmp/chrome-command-line' > /dev/null
  shell am set-debug-app --persistent com.android.chrome > /dev/null
  [ "$API" -ge 33 ] && shell pm grant com.android.chrome android.permission.POST_NOTIFICATIONS > /dev/null
  shell am force-stop com.android.chrome > /dev/null
fi

# The screen's text, as accessibility services see it (web pages included)
screen_text() {
  for _ in 1 2 3; do
    shell uiautomator dump /sdcard/africycle-window.xml > /dev/null
    xml=$(shell cat /sdcard/africycle-window.xml)
    if echo "$xml" | grep -q "<hierarchy"; then
      echo "$xml" | grep -o 'text="[^"]*"\|content-desc="[^"]*"' | sed 's/^[a-z-]*="//; s/"$//' | grep -v '^$'
      return
    fi
    sleep 2
  done
}

top_activity() {
  shell dumpsys activity activities | grep -m1 -E "mResumedActivity|topResumedActivity|ResumedActivity:" | sed 's/^ *//'
}

# ---- 2. Open it from its icon and wait for Africycle (the free server may take a minute to wake) ----
adb logcat -c
say "start: $(shell am start -W -n $PKG/.LauncherActivity | grep -E 'Status|Activity:|TotalTime' | tr '\n' ' ')"
shown=""
for _ in $(seq 1 30); do
  sleep 5
  text=$(screen_text)
  if echo "$text" | grep -q -E "Log in|Create an account|Android System WebView|reach the server"; then
    shown=$(echo "$text" | head -20 | tr '\n' '|')
    break
  fi
done
sleep 3
adb exec-out screencap -p > "$OUT/$LABEL.png"
say "on screen: ${shown:-nothing recognisable after 150 s}"
say "top activity: $(top_activity)"
[ -z "$shown" ] && problem "Africycle did not appear"
if echo "$shown" | grep -q "Android System WebView"; then
  say "note: this phone's WebView is too old for the website; the app asks to update it (as designed)"
elif echo "$shown" | grep -q "reach the server"; then
  problem "the app could not reach the website"
fi

# ---- 3. An Africycle link from another app opens in the app ----
say "link: $(shell am start -W -a android.intent.action.VIEW -c android.intent.category.BROWSABLE -d https://afri-cycle.onrender.com/login.html | grep -E 'Status|Activity:' | tr '\n' ' ')"
sleep 5
say "after link, top activity: $(top_activity)"

# ---- 4. Security probes ----
# Another app tries to make Africycle show a different website: it must open Africycle's own page
shell am start -W -n $PKG/.LauncherActivity -a android.intent.action.VIEW -d https://example.com/ > /dev/null
sleep 8
foreign=$(shell dumpsys activity activities | grep -E "Intent \{" | grep -v "$PKG/.LauncherActivity" | grep -c "example.com")
say "foreign link handed to the browser or built-in screen: $foreign time(s)"
[ "$foreign" != "0" ] && problem "another app made Africycle open a foreign website"

# The built-in screen can't be opened by other apps (adb is "another app" here)
direct=$(shell am start -n $PKG/.WebAppActivity)
say "opening the built-in screen from outside: $(echo "$direct" | tail -1)"
echo "$direct" | grep -q -i -E "not exported|Permission Denial|SecurityException" || problem "the built-in screen can be opened by other apps"

# A release build can't be inspected (run-as) and keeps no backups
say "run-as: $(shell run-as $PKG id | head -1)"
flags=$(shell dumpsys package $PKG | grep -m2 -E "^ *(pkgFlags|flags)=" | tr '\n' ' ')
say "package flags: $flags"
echo "$flags" | grep -q DEBUGGABLE && problem "the app is debuggable"
echo "$flags" | grep -q ALLOW_BACKUP && problem "the app allows backups"
say "permissions: $(shell dumpsys package $PKG | grep -E 'android.permission.[A-Z_]+' -o | sort -u | tr '\n' ' ')"

# Android 12 and newer: are africycle links verified as the app's own (assetlinks.json)?
if [ "$API" -ge 31 ]; then
  say "app links: $(shell pm get-app-links $PKG | tr -s ' \n' ' ')"
fi

# ---- 5. Crashes ----
adb logcat -d > "$OUT/$LABEL-logcat.txt" 2>&1
crashes=$(grep -E "FATAL EXCEPTION|ANR in $PKG" -A 12 "$OUT/$LABEL-logcat.txt" | grep -c "$PKG")
say "crashes of $PKG in the log: $crashes"
[ "$crashes" != "0" ] && problem "the app crashed (see $LABEL-logcat.txt)"

if [ ${#problems[@]} -eq 0 ]; then
  say "RESULT: PASS"
  exit 0
fi
say "RESULT: FAIL (${#problems[@]} problem(s))"
exit 1
