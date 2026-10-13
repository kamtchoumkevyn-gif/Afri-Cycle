import binascii

from flask import Blueprint, jsonify, request

import webpush
from auth_utils import get_user_from_token
from models.push_subscription import delete_subscription, save_subscription

push_bp = Blueprint("push_bp", __name__)


def valid_key(text, length, first_byte=None):
    if not isinstance(text, str) or len(text) > 200:
        return False
    try:
        raw = webpush.from_b64url(text)
    except (binascii.Error, ValueError):
        return False
    return len(raw) == length and (first_byte is None or raw[0] == first_byte)


@push_bp.route("/push/key", methods=["GET"])
def public_key():
    """The app's public key; the browser needs it to sign up for notifications."""
    if not get_user_from_token():
        return jsonify({"message": "Unauthorized"}), 401
    return jsonify({"publicKey": webpush.application_server_key()}), 200


@push_bp.route("/push/subscribe", methods=["POST"])
def subscribe():
    """Saves this device so the logged-in account gets notifications on it.
    Body: the browser's PushSubscription as JSON ({endpoint, keys: {p256dh, auth}})."""
    payload = get_user_from_token()
    if not payload:
        return jsonify({"message": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")
    keys = data.get("keys") if isinstance(data.get("keys"), dict) else {}
    if not webpush.is_push_service(endpoint):
        return jsonify({"message": "That isn't a notification address from a known browser push service"}), 400
    # p256dh: the device's public key (65 bytes starting with 4); auth: a 16-byte secret
    if not valid_key(keys.get("p256dh"), 65, first_byte=4) or not valid_key(keys.get("auth"), 16):
        return jsonify({"message": "keys.p256dh and keys.auth are missing or malformed"}), 400

    save_subscription(payload["userId"], endpoint, keys["p256dh"], keys["auth"])
    return jsonify({"message": "Notifications are on for this device"}), 201


@push_bp.route("/push/subscribe", methods=["DELETE"])
def unsubscribe():
    """Stops notifications on this device (called when turning them off or logging out)."""
    payload = get_user_from_token()
    if not payload:
        return jsonify({"message": "Unauthorized"}), 401
    endpoint = (request.get_json(silent=True) or {}).get("endpoint")
    if not isinstance(endpoint, str):
        return jsonify({"message": "endpoint is required"}), 400
    delete_subscription(endpoint, payload["userId"])
    return jsonify({"message": "Notifications are off for this device"}), 200
