import math

from flask import Blueprint, request, jsonify

import alerts
from access import account_id, is_public_buyer
from auth_utils import get_user_from_token, guardian_block
from database.db import get_connection
from models.notification import create_notification, find_active_notification, update_status
from i18n import _

seller_bp = Blueprint("seller_bp", __name__)


def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(d_lng / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def require_seller():
    """(payload, None) for a seller allowed to trade, else (None, error response)."""
    payload = get_user_from_token()
    if not payload or payload.get("role") not in ("seller", "both"):
        return None, (jsonify({"message": _("Unauthorized")}), 401)
    blocked = guardian_block(payload["userId"])
    if blocked:
        return None, blocked
    return payload, None


@seller_bp.route("/seller/nearby-buyers", methods=["GET"])
def nearby_buyers():
    payload, error = require_seller()
    if error:
        return error

    seller_lat = request.args.get("lat", type=float)
    seller_lng = request.args.get("lng", type=float)
    material_category_id = request.args.get("materialCategoryId", type=int)
    radius_km = request.args.get("radiusKm", default=25, type=float)

    if seller_lat is None or seller_lng is None:
        return jsonify({"message": "lat and lng are required"}), 400

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT bp.userId AS buyerId, u.name AS buyerName,
               bp.latitude, bp.longitude, bp.workingHours,
               pr.materialCategoryId, pr.pricePerKg
        FROM buyer_profile bp
        JOIN users u ON u.id = bp.userId
        JOIN buyer_prices pr ON pr.buyerId = bp.userId
        WHERE u.role IN ('buyer', 'both') AND COALESCE(u.isFlagged, 0) = 0
    """
    params = ()
    if material_category_id:
        query += " AND pr.materialCategoryId = ?"
        params = (material_category_id,)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        distance = haversine_km(seller_lat, seller_lng, row["latitude"], row["longitude"])
        if distance <= radius_km:
            results.append({
                "buyerId": row["buyerId"],
                "buyerName": row["buyerName"],
                "distanceKm": round(distance, 2),
                "pricePerKg": row["pricePerKg"],
                "materialCategoryId": row["materialCategoryId"],
                "workingHours": row["workingHours"],
                "latitude": row["latitude"],
                "longitude": row["longitude"]
            })

    results.sort(key=lambda b: b["pricePerKg"], reverse=True)
    return jsonify({"buyers": results}), 200


@seller_bp.route("/seller/buyer-profile/<int:buyer_id>", methods=["GET"])
def buyer_profile_view(buyer_id):
    payload, error = require_seller()
    if error:
        return error
    if not is_public_buyer(buyer_id):  # never a seller's, child's, guardian's or admin's details
        return jsonify({"message": _("Buyer not found")}), 404

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT u.id AS buyerId, u.name, u.phoneNumber, bp.latitude, bp.longitude, bp.workingHours
        FROM users u
        JOIN buyer_profile bp ON bp.userId = u.id
        WHERE u.id = ?
        """,
        (buyer_id,)
    )
    buyer = cursor.fetchone()

    if not buyer:
        conn.close()
        return jsonify({"message": _("Buyer not found")}), 404

    cursor.execute(
        """
        SELECT p.materialCategoryId, p.pricePerKg, m.name AS materialName, ph.id AS photoId
        FROM buyer_prices p
        LEFT JOIN material_category m ON m.id = p.materialCategoryId
        LEFT JOIN material_photos ph
               ON ph.buyerId = p.buyerId AND ph.materialCategoryId = p.materialCategoryId
        WHERE p.buyerId = ?
        ORDER BY p.pricePerKg DESC
        """,
        (buyer_id,)
    )
    prices = [dict(row) for row in cursor.fetchall()]
    conn.close()

    profile = dict(buyer)
    profile["prices"] = prices
    return jsonify(profile), 200


@seller_bp.route("/seller/notify-buyer", methods=["POST"])
def notify_buyer():
    """Tells a buyer the seller is bringing a material. With onTheWay (sent when the
    seller taps the buyer's photo of that material) the trip starts as "in transit",
    so the seller's live location is shared straight away."""
    payload, error = require_seller()
    if error:
        return error

    data = request.get_json() or {}
    buyer_id = data.get("buyerId")
    material_category_id = data.get("materialCategoryId")
    on_the_way = data.get("onTheWay") is True

    if not buyer_id or not material_category_id:
        return jsonify({"message": "buyerId and materialCategoryId are required"}), 400
    if buyer_id == payload["userId"]:
        return jsonify({"message": _("You cannot notify yourself")}), 400
    if not is_public_buyer(buyer_id):
        return jsonify({"message": _("Buyer not found")}), 404
    material_category_id = account_id(material_category_id)
    material = None
    if material_category_id is not None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM material_category WHERE id = ?", (material_category_id,))
        material = cursor.fetchone()
        conn.close()
    if not material:
        return jsonify({"message": _("Material not found")}), 404

    status = "in transit" if on_the_way else "pending"

    # A double tap shouldn't send the buyer two alerts: reuse the unfinished trip
    existing = find_active_notification(payload["userId"], buyer_id, material_category_id)
    if existing:
        if on_the_way and existing["status"] == "pending":
            update_status(existing["id"], "in transit")
            existing["status"] = "in transit"
            alerts.trip_update(existing["id"], "in transit")
        return jsonify({"message": _("Buyer already notified"), "notificationId": existing["id"],
                        "status": existing["status"]}), 200

    notification_id = create_notification(
        seller_id=payload["userId"],
        buyer_id=buyer_id,
        material_category_id=material_category_id,
        status=status
    )
    alerts.trip_update(notification_id, status)  # a phone notification, if the buyer turned them on
    return jsonify({"message": _("Buyer notified"), "notificationId": notification_id,
                    "status": status}), 201


@seller_bp.route("/seller/contact-buyer/<int:buyer_id>", methods=["GET"])
def contact_buyer(buyer_id):
    payload, error = require_seller()
    if error:
        return error
    if not is_public_buyer(buyer_id):  # only buyers' numbers are public, never anyone else's
        return jsonify({"message": _("Buyer not found")}), 404

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT phoneNumber FROM users WHERE id = ?", (buyer_id,))
    buyer = cursor.fetchone()
    conn.close()

    if not buyer:
        return jsonify({"message": _("Buyer not found")}), 404

    return jsonify({"phoneNumber": buyer["phoneNumber"]}), 200
