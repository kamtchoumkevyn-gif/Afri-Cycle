import os
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS

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

CORS(app)
limiter.init_app(app)

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
    return send_from_directory(FRONTEND_DIR, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
