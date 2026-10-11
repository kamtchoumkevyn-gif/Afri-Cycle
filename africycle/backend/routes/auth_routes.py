from flask import Blueprint, request, jsonify
import jwt
import re
from datetime import datetime, timedelta
from config import Config
from extensions import limiter
from models.user import create_user, find_user_by_phone, verify_login


auth_bp = Blueprint("auth_bp", __name__)


def normalize_phone(phone_number):
    """Turns '+237 6XX XX XX XX' or '2376XXXXXXXX' into the 9-digit form '6XXXXXXXX'."""
    phone_number = str(phone_number).strip().replace(" ", "")
    if phone_number.startswith("+237"):
        phone_number = phone_number[4:]
    elif phone_number.startswith("237") and len(phone_number) == 12:
        phone_number = phone_number[3:]
    return phone_number


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    name = data.get("name")
    phone_number = data.get("phoneNumber")
    password = data.get("password")
    role = data.get("role")

    if not all([name, phone_number, password, role]):
        return jsonify({"message": "name, phoneNumber, password, and role are required"}), 400

    phone_number = normalize_phone(phone_number)
    if not re.fullmatch(r"[26]\d{8}", phone_number):
        return jsonify({"message": "Enter a valid Cameroon phone number, e.g. 6XXXXXXXX"}), 400

    if role not in ("seller", "buyer", "both", "admin"):
        return jsonify({"message": "role must be seller, buyer, both, or admin"}), 400

    if len(password) < 6:
        return jsonify({"message": "Password must be at least 6 characters"}), 400

    admin_numbers = {normalize_phone(number) for number in Config.ADMIN_PHONE_NUMBERS}
    if role == "admin" and phone_number not in admin_numbers:
        return jsonify({"message": "This phone number is not authorized to register as admin"}), 403

    if find_user_by_phone(phone_number):
        return jsonify({"message": "An account with this phone number already exists"}), 400

    user_id = create_user(phone_number, password, name, role)
    return jsonify({"message": "Account created", "userId": user_id}), 201


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    data = request.get_json() or {}
    phone_number = data.get("phoneNumber")
    password = data.get("password")

    if not phone_number or not password:
        return jsonify({"message": "phoneNumber and password are required"}), 400

    # New accounts are saved as 9 digits; accounts created before that rule keep
    # the format they were typed in, so fall back to the number exactly as typed.
    # str(): a number sent as JSON must be compared as text (Postgres won't mix types).
    as_typed = str(phone_number).strip()
    normalized = normalize_phone(as_typed)
    user = verify_login(normalized, password)
    if not user and normalized != as_typed:
        user = verify_login(as_typed, password)
    if not user:
        return jsonify({"message": "Invalid phone number or password"}), 401

    # Optional role from the login form; a "both" account may enter as seller or buyer
    selected_role = data.get("role")
    if selected_role and selected_role != user["role"]:
        if not (user["role"] == "both" and selected_role in ("seller", "buyer")):
            return jsonify({"message": f"This account is registered as {user['role']}. Choose that role to log in."}), 403

    payload = {
        "userId": user["id"],
        "role": user["role"],
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=Config.JWT_EXPIRY_HOURS)
    }
    token = jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")

    return jsonify({
        "message": "Login successful",
        "token": token,
        "role": user["role"],
        "userId": user["id"],
        "name": user["name"]
    }), 200
