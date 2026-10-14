#!/usr/bin/env bash
# After the Gradle build: checks the APK and gathers what the release needs into <out>.
#   Africycle.apk                 signed with the release key (when the build had it)
#   Africycle-unsigned.apk        otherwise: to be signed with apksigner (see README)
#   Africycle-ci-test-only.apk    signed with a key made for this run, for the emulator tests
#   apk-report.txt                versions, permissions, signatures, alignment
set -euo pipefail
OUT=$1
APP=africycle/android/app
BT=$(ls -d "$ANDROID_HOME"/build-tools/* | sort -V | tail -1)
mkdir -p "$OUT"
REPORT="$OUT/apk-report.txt"
: > "$REPORT"

signed=$APP/build/outputs/apk/release/app-release.apk
unsigned=$APP/build/outputs/apk/release/app-release-unsigned.apk
if [ -f "$signed" ]; then apk=$signed; else apk=$unsigned; fi

{
  echo "== $(basename "$apk") ($(stat -c %s "$apk") bytes), build tools $(basename "$BT")"
  echo "== badging"
  "$BT"/aapt2 dump badging "$apk" | grep -E "^package:|sdkVersion|targetSdkVersion|uses-permission|application-label:|launchable-activity|native-code|locales|densities"
  echo "== alignment (resources.arsc must be stored and 4-byte aligned for Android 11+)"
  "$BT"/zipalign -c -P 16 -v 4 "$apk" | grep -E "resources.arsc|Verification" || true
} >> "$REPORT" 2>&1

if [ -f "$signed" ]; then
  cp "$signed" "$OUT/Africycle.apk"
  echo "== signatures" >> "$REPORT"
  "$BT"/apksigner verify --verbose --print-certs --min-sdk-version 21 "$OUT/Africycle.apk" >> "$REPORT" 2>&1
  cp "$OUT/Africycle.apk" "$OUT/Africycle-ci-test-only.apk"
else
  cp "$unsigned" "$OUT/Africycle-unsigned.apk"
  # A key that exists only for this run: lets the emulators install the app. Never published.
  # (With it, Chrome can't match the website's assetlinks.json and shows its address bar.)
  pass=$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9')
  keytool -genkeypair -keystore "$RUNNER_TEMP/ci-test.p12" -storetype PKCS12 -storepass "$pass" \
    -alias ci -keyalg RSA -keysize 2048 -validity 2 -dname "CN=Africycle CI test only" > /dev/null 2>&1
  "$BT"/apksigner sign --ks "$RUNNER_TEMP/ci-test.p12" --ks-pass "pass:$pass" --ks-key-alias ci \
    --min-sdk-version 21 --out "$OUT/Africycle-ci-test-only.apk" "$unsigned"
  rm -f "$RUNNER_TEMP/ci-test.p12" "$OUT"/*.idsig
  echo "== signatures (test key)" >> "$REPORT"
  "$BT"/apksigner verify --verbose --min-sdk-version 21 "$OUT/Africycle-ci-test-only.apk" >> "$REPORT" 2>&1
fi

for report in "$APP"/build/reports/lint-results-release.*; do
  [ -f "$report" ] && cp "$report" "$OUT/"
done
cp "$APP"/build/reports/lint-results.txt "$OUT/lint-results.txt" 2>/dev/null || true
cat "$REPORT"
