"""Parents and guardians supervising under-18 sellers.

A child registers with the guardian's phone number. Any adult account logged in
with that number (a "guardian" account, or a buyer/seller who is also a parent)
can approve or decline the child, then follow their deliveries, sales and messages.
"""
from datetime import datetime

from flask import Blueprint, jsonify
from auth_utils import get_user_from_token
from database.db import get_connection
from models.chat import get_conversation, get_conversations_for_user
from models.user import get_user_by_id
from routes.auth_routes import normalize_phone

guardian_bp = Blueprint("guardian_bp", __name__)

CHILD_FIELDS = "id, name, phoneNumber, guardianRelation, guardianStatus, guardianApprovedAt"


def current_guardian():
    """The logged-in adult, or None. Children can't supervise other children."""
    payload = get_user_from_token()
    user = get_user_by_id(payload["userId"]) if payload else None
    if not user or user.get("isMinor"):
        return None
    return user


def child_for(guardian, child_id, status):
    """The child's account if this guardian may act on it in that status, else None."""
    child = get_user_by_id(child_id)
    if not child or not child.get("isMinor") or child.get("guardianStatus") != status:
        return None
    if status == "pending":
        allowed = child.get("guardianPhone") == normalize_phone(guardian["phoneNumber"])
    else:
        allowed = child.get("guardianId") == guardian["id"]
    return child if allowed else None


@guardian_bp.route("/guardian/children", methods=["GET"])
def list_children():
    guardian = current_guardian()
    if not guardian:
        return jsonify({"message": "Unauthorized"}), 401

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""SELECT {CHILD_FIELDS} FROM users
            WHERE isMinor = 1 AND guardianStatus = 'pending' AND guardianPhone = ?
            ORDER BY id DESC""",
        (normalize_phone(guardian["phoneNumber"]),)
    )
    pending = [dict(row) for row in cursor.fetchall()]
    cursor.execute(
        f"""SELECT {CHILD_FIELDS} FROM users
            WHERE isMinor = 1 AND guardianStatus = 'approved' AND guardianId = ?
            ORDER BY name""",
        (guardian["id"],)
    )
    children = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"pending": pending, "children": children}), 200


def set_child_status(child_id, status, guardian_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if status == "approved":
        cursor.execute(
            "UPDATE users SET guardianStatus = ?, guardianId = ?, guardianApprovedAt = ? WHERE id = ?",
            (status, guardian_id, datetime.utcnow().isoformat(), child_id)
        )
    else:
        cursor.execute("UPDATE users SET guardianStatus = ? WHERE id = ?", (status, child_id))
    conn.commit()
    conn.close()


@guardian_bp.route("/guardian/children/<int:child_id>/approve", methods=["POST"])
def approve_child(child_id):
    guardian = current_guardian()
    if not guardian:
        return jsonify({"message": "Unauthorized"}), 401
    child = child_for(guardian, child_id, "pending")
    if not child:
        return jsonify({"message": "No account is waiting for your approval"}), 404
    set_child_status(child_id, "approved", guardian["id"])
    return jsonify({"message": f"{child['name']} can now sell on Africycle"}), 200


@guardian_bp.route("/guardian/children/<int:child_id>/decline", methods=["POST"])
def decline_child(child_id):
    guardian = current_guardian()
    if not guardian:
        return jsonify({"message": "Unauthorized"}), 401
    child = child_for(guardian, child_id, "pending")
    if not child:
        return jsonify({"message": "No account is waiting for your approval"}), 404
    set_child_status(child_id, "declined")
    return jsonify({"message": f"{child['name']}'s account was declined"}), 200


@guardian_bp.route("/guardian/children/<int:child_id>/activity", methods=["GET"])
def child_activity(child_id):
    guardian = current_guardian()
    if not guardian:
        return jsonify({"message": "Unauthorized"}), 401
    child = child_for(guardian, child_id, "approved")
    if not child:
        return jsonify({"message": "Child not found"}), 404

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT n.*, b.name AS buyerName, m.name AS materialName,
               bp.latitude AS buyerLatitude, bp.longitude AS buyerLongitude
        FROM notifications n
        JOIN users b ON b.id = n.buyerId
        LEFT JOIN material_category m ON m.id = n.materialCategoryId
        LEFT JOIN buyer_profile bp ON bp.userId = n.buyerId
        WHERE n.sellerId = ?
        ORDER BY n.createdAt DESC
        """,
        (child_id,)
    )
    deliveries = [dict(row) for row in cursor.fetchall()]
    cursor.execute(
        """
        SELECT t.*, b.name AS buyerName, m.name AS materialName
        FROM transactions t
        JOIN users b ON b.id = t.buyerId
        LEFT JOIN material_category m ON m.id = t.materialCategoryId
        WHERE t.sellerId = ?
        ORDER BY t.createdAt DESC
        """,
        (child_id,)
    )
    sales = [dict(row) for row in cursor.fetchall()]

    conversations = get_conversations_for_user(child_id)
    for convo in conversations:
        cursor.execute("SELECT name FROM users WHERE id = ?", (convo["otherUserId"],))
        row = cursor.fetchone()
        convo["otherUserName"] = row["name"] if row else None
    conn.close()

    return jsonify({
        "child": {"id": child["id"], "name": child["name"], "phoneNumber": child["phoneNumber"]},
        "deliveries": deliveries,
        "sales": sales,
        "conversations": conversations,
    }), 200


@guardian_bp.route("/guardian/children/<int:child_id>/messages/<int:other_user_id>", methods=["GET"])
def child_messages(child_id, other_user_id):
    guardian = current_guardian()
    if not guardian:
        return jsonify({"message": "Unauthorized"}), 401
    if not child_for(guardian, child_id, "approved"):
        return jsonify({"message": "Child not found"}), 404

    other = get_user_by_id(other_user_id)
    if not other:
        return jsonify({"message": "User not found"}), 404
    return jsonify({
        "otherUserName": other["name"],
        "messages": get_conversation(child_id, other_user_id),
    }), 200
