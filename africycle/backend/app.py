import os
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from werkzeug.security import safe_str_cmp
from pathlib import Path

from config import Config
from extensions import limiter
from database.db import init_db
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

# Restrict CORS to allowed origins only
allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5000").split(",")
CORS(app, resources={
    r"/*": {
        "origins": allowed_origins,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})
limiter.init_app(app)

# Security headers middleware
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    return response

for blueprint in (auth_bp, buyer_bp, seller_bp, notification_bp, admin_bp, chat_bp, material_bp):
    app.register_blueprint(blueprint)

# Create tables and starter categories on startup (safe to run repeatedly)
init_db()
seed_default_categories()


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def serve_frontend(filename):
    # Prevent directory traversal attacks
    if ".." in filename or filename.startswith("/"):
        return jsonify({"message": "Invalid file path"}), 400

    # Only serve static files (HTML, CSS, JS, images, etc.)
    allowed_extensions = {".html", ".css", ".js", ".json", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2"}
    file_ext = Path(filename).suffix.lower()

    if file_ext not in allowed_extensions:
        return jsonify({"message": "File type not allowed"}), 403

    try:
        return send_from_directory(FRONTEND_DIR, filename)
    except FileNotFoundError:
        return jsonify({"message": "File not found"}), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
