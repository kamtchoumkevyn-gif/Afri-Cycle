"""Phones, tablets and computers: compressed downloads, browser caching, the installable
app (manifest, icons, service worker) and what every page loads."""
import gzip
import json
import os
import re
import shutil

import app as app_module
from app import CONTENT_SECURITY_POLICY, FRONTEND_DIR
from helpers import auth_header, new_user

PAGES = sorted(name for name in os.listdir(FRONTEND_DIR) if name.endswith(".html"))
GZIP = {"Accept-Encoding": "gzip, deflate, br"}


def read_frontend(path, mode="r"):
    with open(os.path.join(FRONTEND_DIR, path), mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def service_worker_files(client):
    body = client.get("/sw.js").get_data(as_text=True)
    return json.loads(re.search(r"const FILES = (.*);", body).group(1))


# ---- Smaller downloads ----

def test_text_files_are_gzipped_for_browsers_that_accept_it(client):
    for path in ("/", "/seller-dashboard.html", "/css/dashboard.css", "/js/buyer-dashboard.js",
                 "/vendor/leaflet/leaflet.js", "/manifest.webmanifest"):
        response = client.get(path, headers=GZIP)
        assert response.status_code == 200, path
        assert response.headers["Content-Encoding"] == "gzip", path
        assert "Accept-Encoding" in response.headers["Vary"], path
        original = read_frontend("index.html" if path == "/" else path[1:], "rb")
        assert gzip.decompress(response.get_data()) == original, path
        assert int(response.headers["Content-Length"]) < len(original), path


def test_leaflet_shrinks_to_under_a_third(client):
    size = len(client.get("/vendor/leaflet/leaflet.js", headers=GZIP).get_data())
    assert size < len(read_frontend("vendor/leaflet/leaflet.js", "rb")) / 3


def test_large_api_answers_are_gzipped_too(client):
    admin = new_user("699999999", "admin", "Admin")
    for i in range(15):
        new_user(f"6771000{i:02d}", "seller", f"Collector number {i}")
    response = client.get("/admin/users", headers={**GZIP, **auth_header(admin, "admin")})
    assert response.status_code == 200
    assert response.headers["Content-Encoding"] == "gzip"
    assert len(json.loads(gzip.decompress(response.get_data()))["users"]) == 16


def test_small_answers_stay_uncompressed(client):
    response = client.get("/material-categories", headers=GZIP)
    assert response.status_code == 401  # needs a login; the short error isn't worth compressing
    assert "Content-Encoding" not in response.headers


def test_no_gzip_unless_the_browser_asks(client):
    response = client.get("/js/api.js")
    assert "Content-Encoding" not in response.headers
    assert response.get_data() == read_frontend("js/api.js", "rb")


def test_images_and_fonts_are_never_gzipped(client):
    for path in ("/icons/icon-192.png", "/assets/Africycle_logo.jpg", "/fonts/archivo-extrabold-latin.woff2"):
        response = client.get(path, headers=GZIP)
        assert response.status_code == 200, path
        assert "Content-Encoding" not in response.headers, path


def test_unchanged_files_get_a_quick_304_after_gzip(client):
    first = client.get("/css/base.css", headers=GZIP)
    etag = first.headers["ETag"]
    assert etag.startswith('W/"')
    again = client.get("/css/base.css", headers={**GZIP, "If-None-Match": etag})
    assert again.status_code == 304
    assert again.get_data() == b""


# ---- Browser caching ----

def test_rarely_changing_files_are_cached_for_30_days(client):
    for path in ("/vendor/leaflet/leaflet.js", "/fonts/archivo-extrabold-latin.woff2", "/icons/icon-192.png",
                 "/assets/Africycle_logo.jpg"):
        assert "max-age=2592000" in client.get(path).headers["Cache-Control"], path


def test_pages_styles_and_scripts_are_checked_on_every_visit(client):
    for path in ("/", "/login.html", "/css/base.css", "/js/seller-dashboard.js", "/sw.js"):
        assert "no-cache" in client.get(path).headers["Cache-Control"], path


def test_right_file_types_for_browsers_with_nosniff(client):
    assert client.get("/fonts/archivo-extrabold-latin.woff2").mimetype == "font/woff2"
    assert client.get("/manifest.webmanifest").mimetype == "application/manifest+json"
    assert client.get("/js/api.js").mimetype in ("text/javascript", "application/javascript")
    assert client.get("/sw.js").mimetype == "text/javascript"


# ---- Installable app ----

def test_manifest_describes_an_installable_app(client):
    manifest = json.loads(client.get("/manifest.webmanifest").get_data(as_text=True))
    assert manifest["name"] == "Africycle"
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"
    sizes = {(icon["sizes"], icon.get("purpose", "any")) for icon in manifest["icons"]}
    assert {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= sizes
    for icon in manifest["icons"]:
        response = client.get(icon["src"])
        assert response.status_code == 200 and response.mimetype == "image/png", icon["src"]


def test_service_worker_saves_what_pages_need_and_nothing_else(client):
    files = service_worker_files(client)
    assert "/offline.html" in files and "/manifest.webmanifest" in files
    for page in PAGES:
        assert f"/{page}" in files, page
    for path in files:
        assert client.get(path).status_code == 200, path
    assert "/sw.js" not in files
    assert not [f for f in files if f.endswith(("-512.png", "-latin-ext.woff2", ".txt", "LICENSE"))]
    assert not [f for f in files if f.startswith("/vendor/leaflet/images/")]  # the maps use their own dots


def test_every_script_and_style_a_page_uses_is_saved_for_offline(client):
    files = set(service_worker_files(client))
    for page in PAGES:
        html = read_frontend(page)
        for ref in re.findall(r'<(?:script|link)[^>]+(?:src|href)="([^"]+)"', html):
            if ref.endswith((".js", ".css", ".webmanifest")) or "favicon" in ref or "apple-touch" in ref:
                assert "/" + ref.lstrip("/") in files, f"{page}: {ref}"


def test_service_worker_fingerprint_changes_with_any_frontend_change(tmp_path, monkeypatch):
    copy = tmp_path / "frontend"
    shutil.copytree(FRONTEND_DIR, copy)
    monkeypatch.setattr(app_module, "FRONTEND_DIR", str(copy))
    first = app_module.build_service_worker()
    assert app_module.build_service_worker() == first  # same files, same worker
    css = copy / "css" / "base.css"
    css.write_text(css.read_text() + "\n/* change */\n")
    changed = app_module.build_service_worker()
    build = re.compile(r'const BUILD = "([0-9a-f]{16})"')
    assert build.search(first).group(1) != build.search(changed).group(1)


def test_service_worker_never_touches_the_api():
    template = read_frontend("sw.js")
    # Only GET requests for the listed files (or page loads) are answered from the device
    assert 'request.method !== "GET"' in template
    assert "!FILES.includes(path)" in template


def test_csp_allows_the_service_worker_and_manifest():
    assert "worker-src 'self'" in CONTENT_SECURITY_POLICY
    assert "manifest-src 'self'" in CONTENT_SECURITY_POLICY


# ---- Every page ----

def test_every_page_is_ready_for_phones_and_installing():
    for page in PAGES:
        html = read_frontend(page)
        assert 'name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"' in html, page
        assert 'name="theme-color"' in html, page
        if page == "offline.html":
            continue
        assert 'rel="manifest" href="manifest.webmanifest"' in html, page
        assert 'rel="apple-touch-icon"' in html, page
        assert "<noscript>" in html, page
        scripts = re.findall(r'<script src="([^"]+)"', html)
        # The browser check runs before anything else, and the app helper last
        assert scripts[:2] == ["js/probe.js", "js/compat.js"], page
        assert scripts[-1] == "js/pwa.js", page


def test_pages_never_block_pinch_zoom():
    for page in PAGES:
        viewport = re.search(r'name="viewport" content="([^"]+)"', read_frontend(page)).group(1)
        assert "user-scalable=no" not in viewport and "maximum-scale" not in viewport, page


def test_compat_script_is_plain_old_javascript():
    # compat.js must run in browsers too old for the rest of the app
    source = read_frontend("js/compat.js")
    code = re.sub(r"//.*", "", source)
    for modern in ("=>", "const ", "let ", "`", "class ", "async ", "...", "?."):
        assert modern not in code, modern
