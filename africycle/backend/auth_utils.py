import jwt
from flask import request, jsonify
from config import Config
from database.db import get_connection
from i18n import _


def get_user_from_token():
    """The logged-in account's token payload, or None.

    The token is checked against the account as it is now, not as it was at login: a
    deleted or flagged (suspended) account is logged out at once, and the role comes
    from the database, so a token can't keep a role the account no longer has."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
    except jwt.InvalidTokenError:  # also covers an expired token
        return None

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role, isFlagged, totpEnabled FROM users WHERE id = ?", (payload.get("userId"),))
    row = cursor.fetchone()
    conn.close()
    if not row or row["isFlagged"]:
        return None
    payload["role"] = row["role"]
    # Admin tools need the second step: a code from the authenticator app at this login
    payload["twoStep"] = bool(row["totpEnabled"]) and payload.get("mfa") is True
    return payload


def client_ip():
    """The address the request came from (behind Render's proxy, see app.py)."""
    return request.remote_addr


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
        message = _("Your guardian declined this account, so it can't be used to sell.")
    else:
        message = _("Your guardian needs to approve your account before you can sell. "
                    "Ask them to log in to Africycle with the phone number you gave.")
    return jsonify({"message": message, "code": "guardian_approval_required"}), 403
