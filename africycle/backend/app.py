import os
from flask import Flask, send_from_directory, jsonify
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

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

app = Flask(__name__, static_folder=None)
app.config.from_object(Config)

# Open CORS is safe here: logins use Bearer tokens (not cookies), and in production
# the frontend is served by this same app. It also keeps local testing working when
# the HTML files are opened straight from disk (file://).
CORS(app)
limiter.init_app(app)

for blueprint in (auth_bp, buyer_bp, seller_bp, notification_bp, admin_bp, chat_bp, material_bp):
    app.register_blueprint(blueprint)

# Create tables and starter categories on startup (safe to run repeatedly)
init_db()
seed_default_categories()

# Content-Security-Policy: browsers only run scripts served by this site, so an
# injected <script> or onerror="..." can't run. Google Fonts is the only outside
# source the pages use. The sha256 value allows the small inline <script> at the
# bottom of index.html; if you edit that script, the browser console prints the
# new hash to paste here. Adding a CDN library (e.g. a map)? Add its domain here.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'sha256-WIQm8E+nKtoHRkpBpRcJ+6e8TN00KPKyhiQH/kvOHQA='",
    "style-src 'self' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
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


@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


# send_from_directory refuses any path that leads outside FRONTEND_DIR
# (e.g. /../backend/.env gets a 404), so this can't leak backend files.
@app.route("/<path:filename>")
def serve_frontend(filename):
    return send_from_directory(FRONTEND_DIR, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
