import gzip
import hashlib
import json
import mimetypes
import os

from flask import Flask, jsonify, make_response, request, send_from_directory
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

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

# File types some systems don't know; browsers need the right one (nosniff is on)
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")

app = Flask(__name__, static_folder=None)
app.config.from_object(Config)
# Requests over 1 MB are refused (413). Photos are shrunk to well under this first.
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

# Open CORS is safe here: logins use Bearer tokens (not cookies), and in production
# the frontend is served by this same app. It also keeps local testing working when
# the HTML files are opened straight from disk (file://).
CORS(app)
limiter.init_app(app)

for blueprint in (auth_bp, buyer_bp, seller_bp, notification_bp, admin_bp, chat_bp,
                  material_bp, guardian_bp, directions_bp, push_bp):
    app.register_blueprint(blueprint)

# Create tables and starter categories on startup (safe to run repeatedly)
init_db()
seed_default_categories()

# Content-Security-Policy: browsers only run scripts served by this site, so an
# injected <script> or onerror="..." can't run. Fonts, styles and the map library
# (frontend/vendor) all come from this site too; the one outside source is
# OpenStreetMap's map tiles. blob: lets pages show material photos fetched with the
# login token. The sha256 value allows the small inline <script> at the bottom of
# index.html; if you edit that script, the browser console prints the new hash to
# paste here. Adding another outside library? Add its domain here.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'sha256-WIQm8E+nKtoHRkpBpRcJ+6e8TN00KPKyhiQH/kvOHQA='",
    "style-src 'self'",
    "font-src 'self'",
    "img-src 'self' data: blob: https://tile.openstreetmap.org",
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
    return jsonify({"status": "ok", "database": database}), 200


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


# ---- The website ----

# Files that change rarely (map library, fonts, icons, logo) may be kept by browsers for
# 30 days. Pages, styles and scripts are checked on each visit (a quick 304 when unchanged),
# so a deploy shows up straight away.
LONG_CACHE_FOLDERS = ("vendor/", "fonts/", "icons/", "assets/")
LONG_CACHE_SECONDS = 30 * 24 * 60 * 60


@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html", max_age=0)


# send_from_directory refuses any path that leads outside FRONTEND_DIR
# (e.g. /../backend/.env gets a 404), so this can't leak backend files.
@app.route("/<path:filename>")
def serve_frontend(filename):
    max_age = LONG_CACHE_SECONDS if filename.startswith(LONG_CACHE_FOLDERS) else 0
    return send_from_directory(FRONTEND_DIR, filename, max_age=max_age)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
