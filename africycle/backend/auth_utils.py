import jwt
from flask import request, jsonify
from config import Config
from database.db import get_connection


def get_user_from_token():
    """Pulls the JWT from the Authorization header and returns its payload, or None."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ")[1]
    try:
        return jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def guardian_block(user_id):
    """A 403 response if this is a child's account its guardian hasn't approved, else None.
    Checked on every trading action, so approval takes effect without logging in again."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT isMinor, guardianStatus FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row["isMinor"] or row["guardianStatus"] == "approved":
        return None
    if row["guardianStatus"] == "declined":
        message = "Your guardian declined this account, so it can't be used to sell."
    else:
        message = ("Your guardian needs to approve your account before you can sell. "
                   "Ask them to log in to Africycle with the phone number you gave.")
    return jsonify({"message": message, "code": "guardian_approval_required"}), 403
