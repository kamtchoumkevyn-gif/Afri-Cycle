from flask import Blueprint, request, jsonify
import math
from auth_utils import get_user_from_token
from database.db import get_connection
from models.notification import create_notification

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


@seller_bp.route("/seller/nearby-buyers", methods=["GET"])
def nearby_buyers():
    payload = get_user_from_token()
    if not payload or payload.get("role") not in ("seller", "both"):
        return jsonify({"message": "Unauthorized"}), 401

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
    """
    params = ()
    if material_category_id:
        query += " WHERE pr.materialCategoryId = ?"
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
                "workingHours": row["workingHours"]
            })

    results.sort(key=lambda b: b["pricePerKg"], reverse=True)
    return jsonify({"buyers": results}), 200


@seller_bp.route("/seller/buyer-profile/<int:buyer_id>", methods=["GET"])
def buyer_profile_view(buyer_id):
    payload = get_user_from_token()
    if not payload or payload.get("role") not in ("seller", "both"):
        return jsonify({"message": "Unauthorized"}), 401

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
        return jsonify({"message": "Buyer not found"}), 404

    cursor.execute(
        """
        SELECT p.materialCategoryId, p.pricePerKg, m.name AS materialName
        FROM buyer_prices p
        LEFT JOIN material_category m ON m.id = p.materialCategoryId
        WHERE p.buyerId = ?
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
    payload = get_user_from_token()
    if not payload or payload.get("role") not in ("seller", "both"):
        return jsonify({"message": "Unauthorized"}), 401

    data = request.get_json() or {}
    buyer_id = data.get("buyerId")
    material_category_id = data.get("materialCategoryId")

    if not buyer_id or not material_category_id:
        return jsonify({"message": "buyerId and materialCategoryId are required"}), 400

    notification_id = create_notification(
        seller_id=payload["userId"],
        buyer_id=buyer_id,
        material_category_id=material_category_id
    )
    return jsonify({"message": "Buyer notified", "notificationId": notification_id}), 201


@seller_bp.route("/seller/contact-buyer/<int:buyer_id>", methods=["GET"])
def contact_buyer(buyer_id):
    payload = get_user_from_token()
    if not payload or payload.get("role") not in ("seller", "both"):
        return jsonify({"message": "Unauthorized"}), 401

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT phoneNumber FROM users WHERE id = ?", (buyer_id,))
    buyer = cursor.fetchone()
    conn.close()

    if not buyer:
        return jsonify({"message": "Buyer not found"}), 404

    return jsonify({"phoneNumber": buyer["phoneNumber"]}), 200
