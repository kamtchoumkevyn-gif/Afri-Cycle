"""Parents and guardians supervising under-18 sellers.

A child registers with the guardian's phone number. Any adult account logged in
with that number (a "guardian" account, or a buyer/seller who is also a parent)
can approve or decline the child, then follow their deliveries, sales and messages.

Phone numbers aren't confirmed, so someone else could register with the guardian's
number first. To approve or decline, the guardian also types the 6-digit code shown
on the child's phone. After 5 wrong codes the code stops working, and the child gets
a new one from their own page.
"""
import hmac
import re
from datetime import datetime

from flask import Blueprint, jsonify, request
from auth_utils import get_user_from_token
from database.db import get_connection
from extensions import limiter
from models.chat import get_conversation, get_conversations_for_user
from models.receipt import PHOTO_COUNT
from models.user import APPROVAL_CODE_TRIES, get_user_by_id, new_approval_code, set_approval_code
import phones
from i18n import _

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
        allowed = child.get("guardianPhone") == phones.stored_form(guardian["phoneNumber"])
    else:
        allowed = child.get("guardianId") == guardian["id"]
    return child if allowed else None


@guardian_bp.route("/guardian/children", methods=["GET"])
def list_children():
    guardian = current_guardian()
    if not guardian:
        return jsonify({"message": _("Unauthorized")}), 401

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""SELECT {CHILD_FIELDS} FROM users
            WHERE isMinor = 1 AND guardianStatus = 'pending' AND guardianPhone = ?
            ORDER BY id DESC""",
        (phones.stored_form(guardian["phoneNumber"]),)
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
    """Approved or declined; either way the approval code is used up."""
    conn = get_connection()
    cursor = conn.cursor()
    if status == "approved":
        cursor.execute(
            """UPDATE users SET guardianStatus = ?, guardianId = ?, guardianApprovedAt = ?,
                                approvalCode = NULL, approvalCodeTries = 0 WHERE id = ?""",
            (status, guardian_id, datetime.utcnow().isoformat(), child_id)
        )
    else:
        cursor.execute("UPDATE users SET guardianStatus = ?, approvalCode = NULL, approvalCodeTries = 0 WHERE id = ?",
                       (status, child_id))
    conn.commit()
    conn.close()


def code_error(child):
    """None if the request carries the code shown on the child's phone, else a 400 response.
    Each wrong code counts; the 5th makes the code stop working until the child gets a new one."""
    typed = re.sub(r"\D", "", str((request.get_json(silent=True) or {}).get("code") or ""))
    code = child.get("approvalCode")
    if not code:
        message = _("{name} needs to open Africycle to get a new code first.", name=child["name"])
    elif hmac.compare_digest(typed, code):
        return None
    else:
        tries = (child.get("approvalCodeTries") or 0) + 1
        if tries >= APPROVAL_CODE_TRIES:
            set_approval_code(child["id"], None, tries)
            message = _("Too many wrong codes. Ask {name} to open Africycle and tap New code, then type the new code.",
                        name=child["name"])
        else:
            set_approval_code(child["id"], code, tries)
            message = _("That code doesn't match the one on {name}'s phone. Check it and try again.",
                        name=child["name"])
    return jsonify({"message": message, "code": "approval_code"}), 400


@guardian_bp.route("/guardian/children/<int:child_id>/approve", methods=["POST"])
@limiter.limit("20 per hour")
def approve_child(child_id):
    """Body: {"code": the 6 digits shown on the child's phone}."""
    guardian = current_guardian()
    if not guardian:
        return jsonify({"message": _("Unauthorized")}), 401
    child = child_for(guardian, child_id, "pending")
    if not child:
        return jsonify({"message": _("No account is waiting for your approval")}), 404
    error = code_error(child)
    if error:
        return error
    set_child_status(child_id, "approved", guardian["id"])
    return jsonify({"message": _("{name} can now sell on Africycle", name=child["name"])}), 200


@guardian_bp.route("/guardian/children/<int:child_id>/decline", methods=["POST"])
@limiter.limit("20 per hour")
def decline_child(child_id):
    """Body: {"code": the 6 digits shown on the child's phone}."""
    guardian = current_guardian()
    if not guardian:
        return jsonify({"message": _("Unauthorized")}), 401
    child = child_for(guardian, child_id, "pending")
    if not child:
        return jsonify({"message": _("No account is waiting for your approval")}), 404
    error = code_error(child)
    if error:
        return error
    set_child_status(child_id, "declined")
    return jsonify({"message": _("You declined the account of {name}", name=child["name"])}), 200


@guardian_bp.route("/me/approval-code", methods=["POST"])
@limiter.limit("10 per hour")
def new_code():
    """A child waiting for approval gets a new code (after too many wrong ones)."""
    payload = get_user_from_token()
    child = get_user_by_id(payload["userId"]) if payload else None
    if not child:
        return jsonify({"message": _("Unauthorized")}), 401
    if not child.get("isMinor") or child.get("guardianStatus") != "pending":
        return jsonify({"message": _("Forbidden")}), 403
    code = new_approval_code()
    set_approval_code(child["id"], code)
    return jsonify({"approvalCode": code}), 200


@guardian_bp.route("/guardian/children/<int:child_id>/activity", methods=["GET"])
def child_activity(child_id):
    guardian = current_guardian()
    if not guardian:
        return jsonify({"message": _("Unauthorized")}), 401
    child = child_for(guardian, child_id, "approved")
    if not child:
        return jsonify({"message": _("Child not found")}), 404

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
        f"""
        SELECT t.*, b.name AS buyerName, m.name AS materialName, {PHOTO_COUNT}
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
        return jsonify({"message": _("Unauthorized")}), 401
    if not child_for(guardian, child_id, "approved"):
        return jsonify({"message": _("Child not found")}), 404

    other = get_user_by_id(other_user_id)
    if not other:
        return jsonify({"message": _("User not found")}), 404
    return jsonify({
        "otherUserName": other["name"],
        "messages": get_conversation(child_id, other_user_id),
    }), 200
