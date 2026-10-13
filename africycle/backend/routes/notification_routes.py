import math

from flask import Blueprint, request, jsonify

import alerts
from auth_utils import get_user_from_token
from database.db import get_connection
from models.notification import get_notification_by_id, update_location, update_status

notification_bp = Blueprint("notification_bp", __name__)


def to_number(value, low, high):
    """Returns value as a float if it's a real number from low to high, else None.
    Rejects text, true/false, NaN and Infinity (Python's JSON parser accepts the last two)."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not low <= number <= high:
        return None
    return number

# buyerLatitude/buyerLongitude: where the seller is heading (the buyer's saved buying point)
LIST_QUERY = """
    SELECT n.*, s.name AS sellerName, b.name AS buyerName, m.name AS materialName,
           s.isMinor AS sellerIsMinor, bp.latitude AS buyerLatitude, bp.longitude AS buyerLongitude
    FROM notifications n
    JOIN users s ON s.id = n.sellerId
    JOIN users b ON b.id = n.buyerId
    LEFT JOIN material_category m ON m.id = n.materialCategoryId
    LEFT JOIN buyer_profile bp ON bp.userId = n.buyerId
    WHERE {where}
    ORDER BY n.createdAt DESC
"""


@notification_bp.route("/notifications", methods=["GET"])
def list_notifications():
    """Buyers see notifications they received; sellers see the ones they sent."""
    payload = get_user_from_token()
    if not payload:
        return jsonify({"message": "Unauthorized"}), 401

    role = payload.get("role")
    if role == "buyer":
        where = "n.buyerId = ?"
        params = (payload["userId"],)
    elif role == "seller":
        where = "n.sellerId = ?"
        params = (payload["userId"],)
    elif role == "both":
        where = "n.buyerId = ? OR n.sellerId = ?"
        params = (payload["userId"], payload["userId"])
    else:
        return jsonify({"message": "Unauthorized"}), 401

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(LIST_QUERY.format(where=where), params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"notifications": rows}), 200


@notification_bp.route("/notifications/<int:notification_id>", methods=["GET"])
def get_notification(notification_id):
    payload = get_user_from_token()
    if not payload:
        return jsonify({"message": "Unauthorized"}), 401

    notification = get_notification_by_id(notification_id)
    if not notification:
        return jsonify({"message": "Notification not found"}), 404

    if payload["userId"] not in (notification["buyerId"], notification["sellerId"]):
        return jsonify({"message": "Forbidden"}), 403

    return jsonify(notification), 200


@notification_bp.route("/notifications/<int:notification_id>/location", methods=["PATCH"])
def update_notification_location(notification_id):
    payload = get_user_from_token()
    if not payload:
        return jsonify({"message": "Unauthorized"}), 401

    notification = get_notification_by_id(notification_id)
    if not notification:
        return jsonify({"message": "Notification not found"}), 404

    if notification["sellerId"] != payload["userId"]:
        return jsonify({"message": "Forbidden"}), 403

    data = request.get_json() or {}
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if latitude is None or longitude is None:
        return jsonify({"message": "latitude and longitude are required"}), 400

    # Only real coordinates get stored: the buyer dashboard puts these values into
    # a link's HTML, so unchecked text here would let a seller inject a script.
    latitude = to_number(latitude, -90, 90)
    longitude = to_number(longitude, -180, 180)
    if latitude is None or longitude is None:
        return jsonify({"message": "latitude must be a number from -90 to 90 and longitude from -180 to 180"}), 400

    update_location(notification_id, latitude, longitude)
    return jsonify({"message": "Location updated"}), 200


@notification_bp.route("/notifications/<int:notification_id>/status", methods=["PATCH"])
def update_notification_status(notification_id):
    payload = get_user_from_token()
    if not payload:
        return jsonify({"message": "Unauthorized"}), 401

    notification = get_notification_by_id(notification_id)
    if not notification:
        return jsonify({"message": "Notification not found"}), 404

    if payload["userId"] not in (notification["buyerId"], notification["sellerId"]):
        return jsonify({"message": "Forbidden"}), 403

    data = request.get_json() or {}
    new_status = data.get("status")
    if not new_status:
        return jsonify({"message": "status is required"}), 400

    try:
        update_status(notification_id, new_status)
    except ValueError as e:
        return jsonify({"message": str(e)}), 400

    if payload["userId"] == notification["sellerId"]:
        alerts.trip_update(notification_id, new_status)  # tell the buyer: on the way, or arrived
    return jsonify({"message": "Status updated"}), 200
