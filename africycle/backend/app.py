import gzip
import hashlib
import json
import mimetypes
import os
import re

from flask import Flask, jsonify, make_response, redirect, request, send_from_directory
from flask_cors import CORS

from config import Config
from extensions import limiter
from database.db import init_db, get_connection, using_postgres
from models.material_category import seed_default_categories

from routes.auth_routes import auth_bp
from routes.buyer_routes import buyer_bp
from routes.seller_routes import seller_bp
from routes.notification_routes import notification_bp
from routes.admin_routes import admin_bp
from routes.chat_routes import chat_bp
from routes.material_routes import material_bp
from routes.guardian_routes import guardian_bp
from routes.directions_routes import directions_bp
from routes.push_routes import push_bp
from routes.receipt_routes import receipt_bp
from routes.guide_routes import guide_bp

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

# File types some systems don't know; browsers need the right one (nosniff is on)
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/vnd.android.package-archive", ".apk")  # phones install it, not save it as .zip

app = Flask(__name__, static_folder=None)
app.config.from_object(Config)
# On Render, every request reaches the app through Render's proxy, so without this the
# app would see the proxy's address for everyone: the login limit (5 a minute) would
# then be shared by all users, and one person could lock everybody out. Render adds the
# real address in X-Forwarded-For. Only trusted where Render sets RENDER=true; elsewhere
# anyone could fake that header.
if os.environ.get("RENDER"):
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
# Requests over 1 MB are refused (413). Photos are shrunk to well under this first.
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

# Open CORS is safe here: logins use Bearer tokens (not cookies), and in production
# the frontend is served by this same app. It also keeps local testing working when
# the HTML files are opened straight from disk (file://).
CORS(app)
limiter.init_app(app)

for blueprint in (auth_bp, buyer_bp, seller_bp, notification_bp, admin_bp, chat_bp,
                  material_bp, guardian_bp, directions_bp, push_bp, receipt_bp, guide_bp):
    app.register_blueprint(blueprint)

# Create tables and starter categories on startup (safe to run repeatedly)
init_db()
seed_default_categories()

# Content-Security-Policy: browsers only run scripts served by this site, so an
# injected <script> or onerror="..." can't run. Fonts, styles and the map library
# (frontend/vendor) all come from this site too; the one outside source is
# OpenStreetMap's map tiles. blob: lets pages show material photos fetched with the
# login token, and the voice guide's recording studio play a recording back before
# saving it (media-src). The sha256 value allows the small inline <script> at the
# bottom of index.html; if you edit that script, the browser console prints the new
# hash to paste here. Adding another outside library? Add its domain here.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'sha256-WIQm8E+nKtoHRkpBpRcJ+6e8TN00KPKyhiQH/kvOHQA='",
    "style-src 'self'",
    "font-src 'self'",
    "img-src 'self' data: blob: https://tile.openstreetmap.org",
    "media-src 'self' blob:",
    "connect-src 'self'",
    "worker-src 'self'",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


@app.after_request
def add_security_headers(response):
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if response.mimetype == "application/json" and not request.path.startswith("/i18n/"):
        response.vary.add("Accept-Language")  # API messages come in the language asked for
    return response


# ---- Smaller downloads for slow mobile connections ----

COMPRESSIBLE = {"text/html", "text/css", "text/javascript", "application/javascript",
                "application/json", "application/manifest+json", "image/svg+xml", "text/plain"}


@app.after_request
def compress(response):
    """Gzips pages, styles, scripts and API answers: about 70% less to download.
    Photos, fonts and images are already compressed, so they're left alone."""
    if (response.status_code != 200 or response.mimetype not in COMPRESSIBLE
            or "gzip" not in request.headers.get("Accept-Encoding", "").lower()
            or "Content-Encoding" in response.headers):
        return response
    response.direct_passthrough = False  # files are streamed; read this one into memory
    data = response.get_data()
    if len(data) < 500:
        return response
    response.set_data(gzip.compress(data, compresslevel=6))
    response.headers["Content-Encoding"] = "gzip"
    response.vary.add("Accept-Encoding")
    etag, _weak = response.get_etag()
    if etag:
        # Same file, different bytes on the wire: a weak tag says so, and the browser's
        # "has it changed?" check still gets a quick 304 when it hasn't
        response.set_etag(etag, weak=True)
    return response


# Render sets RENDER_GIT_COMMIT to the commit it deployed. /health shows it, so the
# live-site check (.github/workflows/site.yml) knows when a change is really live.
DEPLOYED_COMMIT = os.environ.get("RENDER_GIT_COMMIT", "").strip()


@app.route("/health")
def health():
    """Also checks the database, so a broken connection shows up as an error."""
    database = "postgres" if using_postgres() else "sqlite"
    try:
        conn = get_connection()
        conn.cursor().execute("SELECT 1")
        conn.close()
    except Exception:
        app.logger.exception("Health check: database unreachable")
        return jsonify({"status": "error", "database": database}), 503
    answer = {"status": "ok", "database": database}
    if DEPLOYED_COMMIT:
        answer["version"] = DEPLOYED_COMMIT
    return jsonify(answer), 200


# ---- Installable app: the service worker ----

def is_saved_on_device(path):
    """Files the service worker keeps on the phone: everything a page needs to open.
    Large icons are fetched only when someone installs the app, extra font files only
    when a page shows letters outside English and French."""
    if path == "sw.js" or path.endswith(("-512.png", "-latin-ext.woff2")):
        return False
    if path.endswith((".html", ".css", ".js", ".webmanifest", ".woff2")):
        return True
    return path.startswith(("icons/", "assets/"))


def build_service_worker():
    """sw.js with BUILD (a fingerprint of every file in frontend/) and FILES filled in.
    Any change to the frontend changes BUILD, which makes browsers install the new
    version and drop the old one: nobody keeps an outdated copy after a deploy."""
    fingerprint = hashlib.sha256()
    saved = []
    for folder, subfolders, names in os.walk(FRONTEND_DIR):
        subfolders.sort()
        for name in sorted(names):
            full_path = os.path.join(folder, name)
            path = os.path.relpath(full_path, FRONTEND_DIR).replace(os.sep, "/")
            with open(full_path, "rb") as f:
                fingerprint.update(path.encode() + b"\0" + f.read())
            if is_saved_on_device(path):
                saved.append("/" + path)
    with open(os.path.join(FRONTEND_DIR, "sw.js"), encoding="utf-8") as f:
        template = f.read()
    return (template.replace("__BUILD__", fingerprint.hexdigest()[:16])
                    .replace("__FILES__", json.dumps(saved)))


SERVICE_WORKER = build_service_worker()


@app.route("/sw.js")
def serve_service_worker():
    response = make_response(SERVICE_WORKER)
    response.headers["Content-Type"] = "text/javascript; charset=utf-8"
    response.headers["Cache-Control"] = "no-cache"  # browsers check for a new version on each visit
    return response


# ---- The Android app (africycle/android) ----

# Chrome shows the app full screen, without an address bar, only after this site confirms the
# app is its own: /.well-known/assetlinks.json names the app's package and the SHA-256
# fingerprint of the certificate it is signed with (see "Android app" in README.md).
# ANDROID_CERT_SHA256 may list several, separated by commas: if the app is ever published on
# Google Play with Play App Signing, add the fingerprint Play shows (App integrity page).
ANDROID_PACKAGE = os.environ.get("ANDROID_PACKAGE", "cm.africycle.app")
ANDROID_CERT_SHA256 = os.environ.get(
    "ANDROID_CERT_SHA256",
    "D9:A1:78:5C:AC:65:DB:3D:A3:79:6A:DF:09:D3:1C:D2:3B:05:68:CB:30:E9:89:24:30:94:0A:B8:4C:B3:08:6D")
# What the "Download the Android app" link on the home page gives: the signed APK kept on this
# site (frontend/downloads/Africycle.apk) when there is one, otherwise ANDROID_APK_URL, the
# newest release on GitHub by default. Setting ANDROID_APK_URL makes the link go there instead.
ANDROID_APK_FILE = os.path.join(FRONTEND_DIR, "downloads", "Africycle.apk")
ANDROID_APK_URL_SET = "ANDROID_APK_URL" in os.environ
ANDROID_APK_URL = os.environ.get(
    "ANDROID_APK_URL",
    "https://github.com/kamtchoumkevyn-gif/Afri-Cycle/releases/latest/download/Africycle.apk")


def certificate_fingerprints(setting):
    """"D9:A1:...", "d9a1..." or several of either, separated by commas, as Android writes
    them: 32 pairs of capital hex digits joined by colons. Anything else is skipped."""
    found = []
    for item in setting.split(","):
        digits = re.sub(r"[^0-9A-Fa-f]", "", item).upper()
        if len(digits) == 64:
            found.append(":".join(digits[i:i + 2] for i in range(0, 64, 2)))
        elif item.strip():
            app.logger.warning("ANDROID_CERT_SHA256: %r is not a SHA-256 fingerprint; skipped", item.strip())
    return found


def asset_links():
    return [{
        "relation": ["delegate_permission/common.handle_all_urls",
                     "delegate_permission/common.get_login_creds"],
        "target": {
            "namespace": "android_app",
            "package_name": ANDROID_PACKAGE,
            "sha256_cert_fingerprints": certificate_fingerprints(ANDROID_CERT_SHA256),
        },
    }]


@app.route("/.well-known/assetlinks.json")
def serve_asset_links():
    response = jsonify(asset_links())
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@app.route("/download/android")
def download_android_app():
    """The Android app (APK): this site's copy, or the GitHub release (see ANDROID_APK_FILE)."""
    if not ANDROID_APK_URL_SET and os.path.isfile(ANDROID_APK_FILE):
        return send_from_directory(os.path.dirname(ANDROID_APK_FILE), "Africycle.apk", max_age=0,
                                   as_attachment=True, download_name="Africycle.apk",
                                   mimetype="application/vnd.android.package-archive")
    return redirect(ANDROID_APK_URL, code=302)


# ---- The website ----

# Files that change rarely (map library, fonts, icons, logo) may be kept by browsers for
# 30 days. Pages, styles and scripts are checked on each visit (a quick 304 when unchanged),
# so a deploy shows up straight away.
LONG_CACHE_FOLDERS = ("vendor/", "fonts/", "icons/", "assets/")
LONG_CACHE_SECONDS = 30 * 24 * 60 * 60
VOICE_CLIP_SECONDS = 365 * 24 * 60 * 60


@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html", max_age=0)


# send_from_directory refuses any path that leads outside FRONTEND_DIR
# (e.g. /../backend/.env gets a 404), so this can't leak backend files.
@app.route("/<path:filename>")
def serve_frontend(filename):
    if filename.startswith("voices/") and filename.endswith(".ogg"):
        # The voice guide's clips are named after what they say: a clip never changes
        response = send_from_directory(FRONTEND_DIR, filename, max_age=VOICE_CLIP_SECONDS)
        response.headers["Cache-Control"] = f"public, max-age={VOICE_CLIP_SECONDS}, immutable"
        return response
    max_age = LONG_CACHE_SECONDS if filename.startswith(LONG_CACHE_FOLDERS) else 0
    return send_from_directory(FRONTEND_DIR, filename, max_age=max_age)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
