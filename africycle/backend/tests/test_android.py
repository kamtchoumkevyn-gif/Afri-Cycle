"""The Android app (africycle/android): the website's side of the link between them
(/.well-known/assetlinks.json and the download), and the app's settings that keep it
installable on every Android version from 5.0, and safe."""
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ElementTree

import pytest

import app as app_module
from app import certificate_fingerprints

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import android_strings  # noqa: E402
import i18n_strings  # noqa: E402

AFRICYCLE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ANDROID = os.path.join(AFRICYCLE, "android")
MAIN = os.path.join(ANDROID, "app", "src", "main")
RES = os.path.join(MAIN, "res")
JAVA = os.path.join(MAIN, "java", "cm", "africycle", "app")
WORKFLOW = os.path.join(AFRICYCLE, "..", ".github", "workflows", "android.yml")
NS = "{http://schemas.android.com/apk/res/android}"
RELEASE_KEY = "D9:A1:78:5C:AC:65:DB:3D:A3:79:6A:DF:09:D3:1C:D2:3B:05:68:CB:30:E9:89:24:30:94:0A:B8:4C:B3:08:6D"


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def manifest():
    return ElementTree.parse(os.path.join(MAIN, "AndroidManifest.xml")).getroot()


def attr(element, name):
    return element.get(NS + name)


def gradle_setting(name):
    return re.search(rf"^\s*{name}\s+(\S+)", read(ANDROID, "app", "build.gradle"), re.M).group(1).strip('"')


# ---- The website's side ----

def test_asset_links_name_the_app_and_its_signing_key(client):
    response = client.get("/.well-known/assetlinks.json")
    assert response.status_code == 200  # no login, no redirect: Chrome and Android fetch it as is
    assert response.mimetype == "application/json"
    assert "max-age" in response.headers["Cache-Control"]
    [statement] = response.get_json()
    assert "delegate_permission/common.handle_all_urls" in statement["relation"]
    assert statement["target"] == {"namespace": "android_app", "package_name": "cm.africycle.app",
                                   "sha256_cert_fingerprints": [RELEASE_KEY]}


def test_fingerprints_are_written_the_way_android_compares_them():
    lower = RELEASE_KEY.replace(":", "").lower()
    second = "AB" * 32
    assert certificate_fingerprints(f"{lower}, {second}") == [RELEASE_KEY, ":".join(["AB"] * 32)]
    assert certificate_fingerprints("not-a-fingerprint, " + RELEASE_KEY) == [RELEASE_KEY]
    assert certificate_fingerprints("") == []


def test_another_key_can_be_added_without_a_code_change(client, monkeypatch):
    play = ":".join(["0F"] * 32)
    monkeypatch.setattr(app_module, "ANDROID_CERT_SHA256", f"{RELEASE_KEY},{play}")
    [statement] = client.get("/.well-known/assetlinks.json").get_json()
    assert statement["target"]["sha256_cert_fingerprints"] == [RELEASE_KEY, play]


def test_the_download_link_leads_to_the_newest_apk(client):
    response = client.get("/download/android")
    assert response.status_code == 302
    assert response.headers["Location"] == \
        "https://github.com/kamtchoumkevyn-gif/Afri-Cycle/releases/latest/download/Africycle.apk"


def test_the_home_page_offers_the_app_on_android_phones_only():
    html = read(AFRICYCLE, "frontend", "index.html")
    assert re.search(r'<a id="androidAppLink" class="btn btn-quiet" href="download/android" hidden>', html)
    assert 'id="androidAppHint" class="field-hint" hidden' in html
    pwa = read(AFRICYCLE, "frontend", "js", "pwa.js")
    assert "/android/i.test(navigator.userAgent)" in pwa and "inAndroidApp()" in pwa
    # The app says who it is: its built-in screen in the user agent, Chrome in the referrer
    api = read(AFRICYCLE, "frontend", "js", "api.js")
    assert r"/\bAfricycleApp\//" in api and '"android-app://cm.africycle.app"' in api
    assert '" AfricycleApp/"' in read(JAVA, "WebAppActivity.java")


# ---- One app, one website: the same names everywhere ----

def test_package_name_and_website_are_the_same_everywhere():
    assert gradle_setting("applicationId") == gradle_setting("namespace") == app_module.ANDROID_PACKAGE
    host = "afri-cycle.onrender.com"
    assert f'HOST = "{host}"' in read(JAVA, "Site.java")
    assert f">https://{host}/<" in read(RES, "values", "strings.xml")
    assert f'\\"site\\": \\"https://{host}\\"' in read(RES, "values", "strings.xml")
    links = [data for data in manifest().iter("data") if attr(data, "scheme") == "https"]
    assert [attr(data, "host") for data in links] == [host]


# ---- Every Android version ----

def test_runs_on_android_5_and_newer_and_follows_the_newest_rules():
    assert int(gradle_setting("minSdk")) == 21  # Android 5.0
    assert int(gradle_setting("targetSdk")) >= 35  # Android 15: required by Google Play since 2025
    assert int(gradle_setting("compileSdk")) >= int(gradle_setting("targetSdk"))
    gradle = read(ANDROID, "app", "build.gradle")
    for scheme in ("enableV1Signing true", "enableV2Signing true", "enableV3Signing true"):
        assert scheme in gradle  # v1 for Android 5-6, v2 for 7 and newer (and required from 11)
    # androidbrowserhelper 2.7 and newer need Android 6.0 or 7.0
    assert "androidbrowserhelper:androidbrowserhelper:2.6." in gradle


def test_every_language_of_the_website_is_in_the_app():
    assert android_strings.out_of_date() == []
    for code in i18n_strings.catalog_codes():
        assert os.path.exists(os.path.join(RES, android_strings.folder_name(code), "strings.xml")), code
    assert android_strings.folder_name("fr") == "values-fr"
    assert android_strings.folder_name("wes") == "values-b+wes"
    assert attr(manifest().find("application"), "supportsRtl") == "true"  # Arabic


def test_android_text_is_escaped_for_android():
    assert android_strings.android_escape("Can't \"go\" & <stay>") == "Can\\'t \\\"go\\\" &amp; &lt;stay&gt;"
    assert android_strings.android_escape("@home") == "\\@home"
    assert i18n_strings.android_unescape("Can\\'t \\\"go\\\"") == "Can't \"go\""


def test_icons_for_every_screen_density_and_android_version():
    for density in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
        for name in ("ic_launcher", "ic_launcher_foreground", "ic_launcher_monochrome"):
            assert os.path.exists(os.path.join(RES, f"mipmap-{density}", f"{name}.png")), (density, name)
        for name in ("ic_notification", "splash"):
            assert os.path.exists(os.path.join(RES, f"drawable-{density}", f"{name}.png")), (density, name)
    adaptive = read(RES, "mipmap-anydpi-v26", "ic_launcher.xml")
    assert "<monochrome" in adaptive  # themed icons, Android 13


# ---- Security ----

def test_asks_only_for_what_it_needs():
    root = manifest()
    permissions = {attr(p, "name") for p in root.iter("uses-permission")}
    assert permissions == {"android.permission.INTERNET", "android.permission.ACCESS_FINE_LOCATION",
                           "android.permission.ACCESS_COARSE_LOCATION", "android.permission.POST_NOTIFICATIONS"}
    # Phones without GPS, a camera or a touch screen can still install it
    assert all(attr(f, "required") == "false" for f in root.iter("uses-feature"))


def test_https_only_and_nothing_copied_to_backups():
    application = manifest().find("application")
    assert attr(application, "allowBackup") == "false"
    assert attr(application, "usesCleartextTraffic") == "false"
    assert attr(application, "networkSecurityConfig") == "@xml/network_security_config"
    config = read(RES, "xml", "network_security_config.xml")
    assert 'cleartextTrafficPermitted="false"' in config and '<certificates src="system" />' in config
    assert '<certificates src="user"' not in config
    rules = ElementTree.parse(os.path.join(RES, "xml", "data_extraction_rules.xml")).getroot()
    for kind in ("cloud-backup", "device-transfer"):  # Android 12 and newer
        excluded = {(e.get("domain"), e.get("path")) for e in rules.find(kind).iter("exclude")}
        assert ("root", ".") in excluded and ("external", ".") in excluded, kind
        assert not list(rules.find(kind).iter("include")), kind
    assert attr(application, "fullBackupContent") == "@xml/backup_rules"  # Android 6.0 to 11
    old_rules = ElementTree.parse(os.path.join(RES, "xml", "backup_rules.xml")).getroot()
    assert ("root", ".") in {(e.get("domain"), e.get("path")) for e in old_rules.iter("exclude")}
    assert not list(old_rules.iter("include"))


def test_only_the_icon_and_the_browser_service_are_open_to_other_apps():
    application = manifest().find("application")
    exported = {attr(c, "name") for c in application if attr(c, "exported") == "true"}
    assert exported == {".LauncherActivity", ".DelegationService"}
    for component in application:
        if component.tag in ("activity", "service", "provider", "receiver"):
            assert attr(component, "exported") in ("true", "false"), attr(component, "name")  # Android 12 needs it said
    provider = application.find("provider")
    assert attr(provider, "exported") == "false" and attr(provider, "grantUriPermissions") == "true"
    paths = read(RES, "xml", "filepaths.xml")
    assert re.findall(r'path="([^"]*)"', paths) == ["twa_splash/", "camera/"]


def test_the_built_in_screen_is_locked_down():
    java = read(JAVA, "WebAppActivity.java")
    for setting in ("setAllowFileAccess(false)", "setAllowContentAccess(false)",
                    "setAllowFileAccessFromFileURLs(false)", "setAllowUniversalAccessFromFileURLs(false)",
                    "setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW)", "setSafeBrowsingEnabled(true)",
                    "setAcceptThirdPartyCookies(view, false)", "handler.cancel()", "request.deny()"):
        assert setting in java, setting
    assert "addJavascriptInterface" not in java
    assert "handler.proceed" not in java
    assert "FLAG_DEBUGGABLE" in java  # remote debugging only in debug builds
    # Pages crash-proof on Android 8+, back gesture on 13+, notches and bars on 15+
    for feature in ("onRenderProcessGone", "OnBackInvokedCallback", "WindowInsets.Type.displayCutout()"):
        assert feature in java, feature


def test_other_apps_cant_send_the_app_to_another_website():
    java = read(JAVA, "LauncherActivity.java")
    assert "setIntent(safeCopy(getIntent()))" in java  # before the library reads it
    assert java.index("setIntent(safeCopy(getIntent()))") < java.index("super.onCreate(savedInstanceState)")
    assert "Site.isOurs(" in java
    site = read(JAVA, "Site.java")
    assert "getEncodedAuthority()" in site  # the whole authority, so user@host tricks fail


def test_the_webview_minimum_matches_what_the_website_needs():
    # js/probe.js names the newest JavaScript the site uses; Chrome 55 has all of it. If the
    # site starts using newer syntax, raise MIN_WEBVIEW_VERSION in WebAppActivity.java too.
    assert "MIN_WEBVIEW_VERSION = 55" in read(JAVA, "WebAppActivity.java")
    probe = read(AFRICYCLE, "frontend", "js", "probe.js")
    assert "async" in probe and "**" in probe and "?." not in probe and "??" not in probe


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_no_signing_key_is_ever_committed():
    listed = subprocess.run(["git", "ls-files"], cwd=AFRICYCLE, capture_output=True, text=True).stdout.split()
    assert not [path for path in listed if path.lower().endswith((".p12", ".jks", ".keystore", ".pfx"))]
    assert not [path for path in listed if "keystore-password" in path]
    ignored = read(AFRICYCLE, ".gitignore")
    for pattern in ("*.jks", "*.keystore", "*.p12"):
        assert pattern in ignored


def test_the_workflow_tests_every_android_version():
    workflow = read(WORKFLOW)
    assert "level >= 21" in workflow and "api-level: ${{ matrix.api }}" in workflow
    assert "device_check.sh" in workflow and os.path.exists(os.path.join(ANDROID, "ci", "device_check.sh"))
    # Third-party actions are pinned to an exact commit
    for action in re.findall(r"uses: (\S+)", workflow):
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", action), action
