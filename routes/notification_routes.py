"""
Notification + chat routes.

NOTE FOR MERGE: this uses a plain @jwt-check pattern. If auth_routes.py already has a '@token_required' decorator, replace 'require_auth' below with that import instead, so there's only one auth mechanism in the app.
"""
from flask import Blueprint, request, jsonify
import jwt
import os
from functools import wraps

from models.notification import (
    get_notification_by_id,
    get_notifications_for_user,
    update_status,
    update_location,
)
from models.chat_message import send_message, get_messages_for_notification

notification_bp = Blueprint("notification_bp", __name__)

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret")

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer"):
            return jsonify({"error": "Missing or Invalid Authorization header"}), 401
        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        request.user = payload
        return f(*args, **kwargs)
    return wrapper

#----------Notification----------

@notification_bp.route("/notifications", methods=["GET"])
@require_auth
def list_notification():
    user_id = request.args.get("userId") or request.user.get("phoneNumber")
    if not user_id:
        return jsonify({"error": "userId is required"}), 400
    return jsonify(get_notifications_for_user(user_id)), 200


@notification_bp.route("/notification/<int:notification_id>/status", methods=["PATCH"])
@require_auth
def patch_status(notification_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if not new_status:
        return jsonify({"error": "status is required"}), 400
    success = update_status(notification_id, new_status)
    if not success:
        return jsonify({"error": "Invalid status or notification not found"}), 400
    return jsonify({"success": True}), 200

@notification_bp.route("/notification/<int:notification_id>/location", methods=["PATCH"])
@require_auth
def patch_location(notification_id):
    data = request.get_json(silent=True) or {}
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if latitude is None or longitude is None:
        return jsonify({"error": "latitude and longitude are required"}), 400
    success = update_location(notification_id, latitude, longitude)
    if not success:
        return jsonify({"error": "Notification not found"}), 404
    return jsonify({"success": True}), 200


#----------chat----------

@notification_bp.route("/notifications/<int:notification_id>/messages", methods=["GET"])
@require_auth
def get_messages(notification_id):
    if get_notification_by_id(notification_id) is None:
        return jsonify({"error": "Notification not found"}), 404
    return jsonify(get_messages_for_notification(notification_id)), 200


@notification_bp.route("/notifications/<int:notification_id>/messages", methods=["POST"])
@require_auth
def post_message(notification_id):
    data = request.get_json(silent=True) or {}
    sender_id = data.get("senderId") or request.user.get("phoneNumber")
    message_text = data.get("messageText")
    
    if not sender_id or not message_text:
        return jsonify({"error": "senderId and messageText are required"}), 400
    
    message = send_message(notification_id, sender_id, message_text)
    if message is None:
        return jsonify({"error": "Could not send message (bad notification or empty text)"}), 400
    
    return jsonify(message), 201