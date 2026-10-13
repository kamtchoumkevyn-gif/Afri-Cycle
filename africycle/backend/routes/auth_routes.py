from flask import Blueprint, request, jsonify
import jwt
from datetime import datetime, timedelta
import phones
from config import Config
from extensions import limiter
from auth_utils import get_user_from_token
from database.db import get_connection
from models.user import (check_password, create_user, find_user_by_phone, find_users_by_phones,
                         get_user_by_id)


auth_bp = Blueprint("auth_bp", __name__)

ROLES = ("seller", "buyer", "both", "admin", "guardian")
GUARDIAN_RELATIONS = ("mother", "father", "grandparent", "aunt or uncle", "older sibling", "other guardian")


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    name = data.get("name")
    phone_number = data.get("phoneNumber")
    password = data.get("password")
    role = data.get("role")

    if not all([name, phone_number, password, role]):
        return jsonify({"message": "name, phoneNumber, password, and role are required"}), 400

    name = str(name).strip()
    if len(name) > 100:
        return jsonify({"message": "Name is too long (max 100 characters)"}), 400

    # Any of the 11 Central African countries; "country" is the one chosen on the page
    # (Cameroon if none was sent). Saved in international form, e.g. +237677123456.
    try:
        country = phones.country_code(data.get("country"))
        phone_number = phones.normalize(phone_number, country)
    except phones.PhoneError as error:
        return jsonify({"message": str(error)}), 400

    if role not in ROLES:
        return jsonify({"message": "role must be seller, buyer, both, guardian, or admin"}), 400

    if len(password) < 6:
        return jsonify({"message": "Password must be at least 6 characters"}), 400

    # Under-18s sell under a guardian's supervision: the guardian approves the
    # account (logging in with this phone number) before the child can trade.
    guardian = None
    if data.get("isMinor") is True:
        if role != "seller":
            return jsonify({"message": "Accounts for under-18s can only be seller accounts"}), 400
        guardian = {
            "name": str(data.get("guardianName") or "").strip(),
            "relation": str(data.get("guardianRelation") or "").strip().lower(),
        }
        if not guardian["name"] or len(guardian["name"]) > 100:
            return jsonify({"message": "Enter your guardian's full name"}), 400
        # The guardian may live in another country of the region than the child
        try:
            guardian["phone"] = phones.normalize(data.get("guardianPhone"),
                                                 data.get("guardianCountry") or country, whose="your guardian's")
        except phones.PhoneError as error:
            return jsonify({"message": str(error)}), 400
        if guardian["phone"] == phone_number:
            return jsonify({"message": "Your guardian's phone number must be different from yours"}), 400
        if guardian["relation"] not in GUARDIAN_RELATIONS:
            return jsonify({"message": "Choose how your guardian is related to you"}), 400

    admin_numbers = {phones.stored_form(number) for number in Config.ADMIN_PHONE_NUMBERS}
    if role == "admin" and phone_number not in admin_numbers:
        return jsonify({"message": "This phone number is not authorized to register as admin"}), 403

    if find_user_by_phone(phone_number):
        return jsonify({"message": "An account with this phone number already exists"}), 400

    user_id = create_user(phone_number, password, name, role, guardian=guardian)
    message = ("Account created. Your guardian must approve it before you can sell."
               if guardian else "Account created")
    return jsonify({"message": message, "userId": user_id}), 201


@auth_bp.route("/me", methods=["GET"])
def me():
    """The logged-in account, its guardian approval status, and how many children it supervises."""
    payload = get_user_from_token()
    user = get_user_by_id(payload["userId"]) if payload else None
    if not user:
        return jsonify({"message": "Unauthorized"}), 401

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*) AS count FROM users
        WHERE isMinor = 1
          AND ((guardianStatus = 'pending' AND guardianPhone = ?)
               OR (guardianStatus = 'approved' AND guardianId = ?))
        """,
        (phones.stored_form(user["phoneNumber"]), user["id"])
    )
    children = cursor.fetchone()["count"]
    conn.close()

    return jsonify({
        "userId": user["id"],
        "name": user["name"],
        "role": user["role"],
        "phoneNumber": user["phoneNumber"],
        "isMinor": bool(user.get("isMinor")),
        "guardianStatus": user.get("guardianStatus"),
        "guardianName": user.get("guardianName"),
        "guardianPhone": user.get("guardianPhone"),
        "childrenCount": children,
    }), 200


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    data = request.get_json() or {}
    phone_number = data.get("phoneNumber")
    password = data.get("password")

    if not phone_number or not password:
        return jsonify({"message": "phoneNumber and password are required"}), 400

    # The number as saved for the country chosen on the page, then for any other country
    # it fits (in case the wrong one was chosen), then exactly as typed (some accounts
    # from before numbers were tidied up). str(): a number sent as JSON is compared as text.
    candidates = find_users_by_phones(phones.lookup_forms(str(phone_number), data.get("country")))
    user = next((account for account in candidates
                 if check_password(str(password), account["passwordHash"])), None)
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
