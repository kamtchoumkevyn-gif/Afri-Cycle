import math

from flask import Blueprint, request, jsonify
from auth_utils import get_user_from_token
from models.buyer_price import set_price as set_price_model
from models.transaction import create_transaction
from models.buyer_profile import (
    create_buyer_profile, get_buyer_profile_by_user_id,
    update_buyer_location, update_working_hours
)
from database.db import get_connection

buyer_bp = Blueprint("buyer_bp", __name__)

MAX_PRICE_PER_KG = 1_000_000
MAX_WEIGHT_KG = 1_000_000


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


@buyer_bp.route("/buyer/set-price", methods=["POST"])
def set_price():
    payload = get_user_from_token()
    if not payload or payload.get("role") not in ("buyer", "both"):
        return jsonify({"message": "Unauthorized"}), 401

    data = request.get_json() or {}
    material_category_id = data.get("materialCategoryId")
    price_per_kg = data.get("pricePerKg")

    if not material_category_id or price_per_kg is None:
        return jsonify({"message": "materialCategoryId and pricePerKg are required"}), 400

    price_per_kg = to_number(price_per_kg, 0, MAX_PRICE_PER_KG)
    if price_per_kg is None:
        return jsonify({"message": "pricePerKg must be a number from 0 to 1,000,000"}), 400

    set_price_model(payload["userId"], material_category_id, price_per_kg)
    return jsonify({"message": "Price updated successfully"}), 200


@buyer_bp.route("/buyer/prices", methods=["GET"])
def list_prices():
    payload = get_user_from_token()
    if not payload or payload.get("role") not in ("buyer", "both"):
        return jsonify({"message": "Unauthorized"}), 401

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.*, m.name AS materialName
        FROM buyer_prices p
        LEFT JOIN material_category m ON m.id = p.materialCategoryId
        WHERE p.buyerId = ?
        ORDER BY m.name
        """,
        (payload["userId"],)
    )
    prices = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"prices": prices}), 200


@buyer_bp.route("/buyer/profile", methods=["GET"])
def get_profile():
    payload = get_user_from_token()
    if not payload or payload.get("role") not in ("buyer", "both"):
        return jsonify({"message": "Unauthorized"}), 401

    profile = get_buyer_profile_by_user_id(payload["userId"])
    return jsonify({"profile": profile}), 200


@buyer_bp.route("/buyer/profile", methods=["POST"])
def save_profile():
    """Creates or updates the buyer's fixed location and working hours."""
    payload = get_user_from_token()
    if not payload or payload.get("role") not in ("buyer", "both"):
        return jsonify({"message": "Unauthorized"}), 401

    data = request.get_json() or {}
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    working_hours = data.get("workingHours")

    if latitude is None or longitude is None:
        return jsonify({"message": "latitude and longitude are required"}), 400

    latitude = to_number(latitude, -90, 90)
    longitude = to_number(longitude, -180, 180)
    if latitude is None or longitude is None:
        return jsonify({"message": "latitude must be a number from -90 to 90 and longitude from -180 to 180"}), 400

    user_id = payload["userId"]
    if get_buyer_profile_by_user_id(user_id):
        update_buyer_location(user_id, latitude, longitude)
        if working_hours is not None:
            update_working_hours(user_id, working_hours)
    else:
        create_buyer_profile(user_id, latitude, longitude, working_hours)

    return jsonify({"message": "Profile saved"}), 200


@buyer_bp.route("/buyer/log-transaction", methods=["POST"])
def log_transaction():
    payload = get_user_from_token()
    if not payload or payload.get("role") not in ("buyer", "both"):
        return jsonify({"message": "Unauthorized"}), 401

    data = request.get_json() or {}
    seller_id = data.get("sellerId")
    material_category_id = data.get("materialCategoryId")
    weight_kg = data.get("weightKg")
    price_per_kg = data.get("pricePerKg")
    photo_url = data.get("photoUrl")

    if not all([seller_id, material_category_id, weight_kg, price_per_kg]):
        return jsonify({"message": "sellerId, materialCategoryId, weightKg, and pricePerKg are required"}), 400

    weight_kg = to_number(weight_kg, 0, MAX_WEIGHT_KG)
    price_per_kg = to_number(price_per_kg, 0, MAX_PRICE_PER_KG)
    if not weight_kg or price_per_kg is None:
        return jsonify({"message": "weightKg must be a number above 0 and pricePerKg from 0 to 1,000,000"}), 400

    transaction_id = create_transaction(
        seller_id, payload["userId"], material_category_id,
        weight_kg, price_per_kg, photo_url
    )
    return jsonify({"message": "Transaction logged", "transactionId": transaction_id}), 201


@buyer_bp.route("/buyer/transaction-history", methods=["GET"])
def transaction_history():
    payload = get_user_from_token()
    if not payload or payload.get("role") not in ("buyer", "both"):
        return jsonify({"message": "Unauthorized"}), 401

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT t.*, u.name AS sellerName, m.name AS materialName
        FROM transactions t
        JOIN users u ON u.id = t.sellerId
        LEFT JOIN material_category m ON m.id = t.materialCategoryId
        WHERE t.buyerId = ?
        ORDER BY t.createdAt DESC
        """,
        (payload["userId"],)
    )
    transactions = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"transactions": transactions}), 200
