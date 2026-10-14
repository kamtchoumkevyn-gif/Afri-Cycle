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
# Every command on the emulator gets at most a minute: an old Android that stops answering
# must not hold up the whole test
shell() { timeout 60 adb shell "$@" 2>&1 | tr -d '\r'; }
problem() { problems+=("$1"); say "PROBLEM: $1"; }

# Android 5 and 6 emulators encrypt their storage on the first start, with a temporary
# Android running meanwhile (whatever is installed then is lost), and restart Android
# when done. Wait for the real one: no encryption under way, booted, package manager up.
wait_for_android() {
  local until=$((SECONDS + 900))
  while [ $SECONDS -lt $until ]; do
    progress=$(shell getprop vold.encrypt_progress)
    phase=$(shell getprop vold.decrypt)
    booted=$(shell getprop sys.boot_completed)
    if [ -z "$progress" ] && [ "$booted" = "1" ] \
       && [ "$phase" != "trigger_restart_min_framework" ] && [ "$phase" != "trigger_shutdown_framework" ] \
       && shell pm path android | grep -q package: && shell pm list packages | grep -q "package:com.android.settings"; then
      return 0
    fi
    sleep 5
  done
  echo "Android did not finish starting"
}

wait_for_android
sleep 10
API=$(shell getprop ro.build.version.sdk)
say "== Africycle on Android $(shell getprop ro.build.version.release) (API $API), $LABEL"
say "storage encryption: $(shell getprop ro.crypto.state) $(shell getprop vold.decrypt)"
say "Chrome: $(shell dumpsys package com.android.chrome | grep -m1 versionName | sed 's/ *//')"
if [ "$API" -ge 24 ]; then
  say "WebView: $(shell dumpsys webviewupdate | grep -m1 -i 'current webview package' | sed 's/^ *//')"
else
  say "WebView: $(shell dumpsys package com.android.webview | grep -m1 versionName | sed 's/ *//')"
fi

# ---- 1. Install ----
installed=$(timeout 300 adb install -r "$APK" 2>&1 | tr -d '\r')
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

# The screen's text, as accessibility services see it (web pages included). uiautomator
# waits for the screen to be still, which a loading page may never be: 25 seconds at most.
screen_text() {
  shell rm -f /sdcard/africycle-window.xml > /dev/null
  timeout 25 adb shell uiautomator dump --compressed /sdcard/africycle-window.xml > /dev/null 2>&1
  shell cat /sdcard/africycle-window.xml | grep -o 'text="[^"]*"\|content-desc="[^"]*"' \
    | sed 's/^[a-z-]*="//; s/"$//' | grep -v '^$'
}

top_activity() {
  shell dumpsys activity activities | grep -m1 -E "mResumedActivity|topResumedActivity|ResumedActivity:" | sed 's/^ *//'
}

# ---- 2. Open it from its icon and wait for Africycle (the free server may take a minute to wake) ----
timeout 30 adb logcat -c
say "start: $(shell am start -W -n $PKG/.LauncherActivity | grep -E 'Status|Activity:|TotalTime' | tr '\n' ' ')"
shown=""
deadline=$((SECONDS + 180))
while [ $SECONDS -lt $deadline ]; do
  sleep 5
  text=$(screen_text)
  if echo "$text" | grep -q -E "Log in|Create an account|Android System WebView|reach the server"; then
    shown=$(echo "$text" | head -20 | tr '\n' '|')
    break
  fi
done
sleep 3
timeout 60 adb exec-out screencap -p > "$OUT/$LABEL.png"
say "on screen: ${shown:-nothing recognisable after 3 minutes}"
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

# Still installed? (If Android restarted underneath the test, say so instead of blaming the app.)
if ! shell pm path $PKG | grep -q package:; then
  problem "the app is no longer installed: the emulator's Android restarted during the test"
fi

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
timeout 120 adb logcat -d > "$OUT/$LABEL-logcat.txt" 2>&1
crashes=$(grep -E "FATAL EXCEPTION|ANR in $PKG" -A 12 "$OUT/$LABEL-logcat.txt" | grep -c "$PKG")
say "crashes of $PKG in the log: $crashes"
[ "$crashes" != "0" ] && problem "the app crashed (see $LABEL-logcat.txt)"

if [ ${#problems[@]} -eq 0 ]; then
  say "RESULT: PASS"
  exit 0
fi
say "RESULT: FAIL (${#problems[@]} problem(s))"
exit 1
