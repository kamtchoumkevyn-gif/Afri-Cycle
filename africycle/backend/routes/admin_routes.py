from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import jwt
import totp
from config import Config
from auth_utils import client_ip, get_user_from_token
from database.db import get_connection
from models.admin_action import log_action, recent_actions
from models.user import get_user_by_id
from i18n import _

admin_bp = Blueprint("admin_bp", __name__)


def admin_or_error():
    """(payload, None) for an admin who logged in with the two-step code, else (None, response).

    An admin who hasn't turned two-step login on yet gets 403 with code
    "two_step_setup": the admin page then shows how to turn it on, and nothing else."""
    payload = get_user_from_token()
    if not payload or payload.get("role") != "admin":
        return None, (jsonify({"message": _("Unauthorized")}), 401)
    if not payload.get("twoStep"):
        return None, (jsonify({"message": _("Turn on two-step login to use the admin tools."),
                               "code": "two_step_setup"}), 403)
    return payload, None


def require_admin():
    """The payload of a fully logged-in admin, or None."""
    return admin_or_error()[0]


def count(cursor, query, params=()):
    cursor.execute(query, params)
    return cursor.fetchone()["count"]


@admin_bp.route("/admin/stats", methods=["GET"])
def user_counts():
    admin, error = admin_or_error()
    if error:
        return error

    today_start = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_connection()
    cursor = conn.cursor()
    stats = {
        "totalUsers": count(cursor, "SELECT COUNT(*) AS count FROM users"),
        "sellerCount": count(cursor, "SELECT COUNT(*) AS count FROM users WHERE role = 'seller'"),
        "buyerCount": count(cursor, "SELECT COUNT(*) AS count FROM users WHERE role = 'buyer'"),
        "adminCount": count(cursor, "SELECT COUNT(*) AS count FROM users WHERE role = 'admin'"),
        "transactionsToday": count(
            cursor, "SELECT COUNT(*) AS count FROM transactions WHERE createdAt >= ?", (today_start,)
        ),
    }
    conn.close()
    return jsonify(stats), 200


@admin_bp.route("/admin/activity-stats", methods=["GET"])
def activity_stats():
    admin, error = admin_or_error()
    if error:
        return error

    seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    conn = get_connection()
    cursor = conn.cursor()

    transactions_7d = count(
        cursor, "SELECT COUNT(*) AS count FROM transactions WHERE createdAt >= ?", (seven_days_ago,)
    )
    notifications_7d = count(
        cursor, "SELECT COUNT(*) AS count FROM notifications WHERE createdAt >= ?", (seven_days_ago,)
    )

    cursor.execute("SELECT status, COUNT(*) AS count FROM notifications GROUP BY status")
    by_status = {row["status"]: row["count"] for row in cursor.fetchall()}

    cursor.execute(
        """
        SELECT m.name AS materialName, COUNT(*) AS count
        FROM transactions t
        LEFT JOIN material_category m ON m.id = t.materialCategoryId
        GROUP BY t.materialCategoryId, m.name
        ORDER BY count DESC
        LIMIT 5
        """
    )
    top_materials = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        "transactionsLast7Days": transactions_7d,
        "notificationsLast7Days": notifications_7d,
        "notificationsByStatus": by_status,
        "topMaterials": top_materials
    }), 200


@admin_bp.route("/admin/users", methods=["GET"])
def list_users():
    admin, error = admin_or_error()
    if error:
        return error

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id AS userId, name, phoneNumber, role, isFlagged, flagReason, isMinor, guardianStatus, totpEnabled "
        "FROM users ORDER BY id DESC"
    )
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"users": users}), 200


@admin_bp.route("/admin/flagged-accounts", methods=["GET"])
def flagged_accounts():
    admin, error = admin_or_error()
    if error:
        return error

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, phoneNumber, role, flagReason FROM users WHERE isFlagged = 1"
    )
    rows = cursor.fetchall()
    conn.close()

    accounts = [
        {
            "userId": row["id"],
            "name": row["name"],
            "phoneNumber": row["phoneNumber"],
            "role": row["role"],
            "reason": row["flagReason"]
        }
        for row in rows
    ]
    return jsonify({"flaggedAccounts": accounts}), 200


@admin_bp.route("/admin/flag-account/<int:user_id>", methods=["POST"])
def flag_account(user_id):
    admin, error = admin_or_error()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason") or "Flagged by admin").strip()[:300]

    target = get_user_by_id(user_id)
    if not target:
        return jsonify({"message": _("User not found")}), 404
    # A flagged account can't log in, so admins can't lock each other (or themselves) out
    if target["role"] == "admin":
        return jsonify({"message": _("Admin accounts can't be flagged")}), 400

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET isFlagged = 1, flagReason = ? WHERE id = ?", (reason, user_id)
    )
    conn.commit()
    conn.close()
    log_action(admin["userId"], "flag", user_id, reason, client_ip())
    return jsonify({"message": _("Account flagged")}), 200


@admin_bp.route("/admin/unflag-account/<int:user_id>", methods=["POST"])
def unflag_account(user_id):
    admin, error = admin_or_error()
    if error:
        return error

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET isFlagged = 0, flagReason = NULL WHERE id = ?", (user_id,)
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()

    if not updated:
        return jsonify({"message": _("User not found")}), 404
    log_action(admin["userId"], "unflag", user_id, ip_address=client_ip())
    return jsonify({"message": _("Account unflagged")}), 200


@admin_bp.route("/admin/actions", methods=["GET"])
def admin_actions():
    """The newest admin actions, for the "Admin activity" table."""
    admin, error = admin_or_error()
    if error:
        return error
    return jsonify({"actions": recent_actions()}), 200


# ---- Two-step login (totp.py) ----

def admin_without_second_step():
    """The logged-in admin's account, whether or not the code was given yet, else None."""
    payload = get_user_from_token()
    if not payload or payload.get("role") != "admin":
        return None
    return get_user_by_id(payload["userId"])


@admin_bp.route("/admin/two-step/setup", methods=["POST"])
def two_step_setup():
    """A new secret for the authenticator app. It only counts once a code from it is
    confirmed (/admin/two-step/enable), so asking again just gives a fresh one."""
    user = admin_without_second_step()
    if not user:
        return jsonify({"message": _("Unauthorized")}), 401
    if user.get("totpEnabled"):
        return jsonify({"message": _("Two-step login is already on")}), 400
    secret = totp.new_secret()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET totpSecret = ? WHERE id = ?", (totp.seal(secret), user["id"]))
    conn.commit()
    conn.close()
    return jsonify({"secret": secret, "link": totp.setup_link(secret, user["phoneNumber"])}), 200


@admin_bp.route("/admin/two-step/enable", methods=["POST"])
def two_step_enable():
    """Turns two-step login on once the app's code matches, and hands back a full admin login."""
    user = admin_without_second_step()
    if not user:
        return jsonify({"message": _("Unauthorized")}), 401
    if user.get("totpEnabled"):
        return jsonify({"message": _("Two-step login is already on")}), 400
    code = (request.get_json(silent=True) or {}).get("code")
    step = totp.check(totp.unseal(user.get("totpSecret") or ""), code)
    if step is None:
        return jsonify({"message": _("That code is wrong or has expired. Type the newest code from the app.")}), 400

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET totpEnabled = 1, totpLastStep = ? WHERE id = ?", (step, user["id"]))
    conn.commit()
    conn.close()
    log_action(user["id"], "two_step_on", ip_address=client_ip())

    token = jwt.encode({
        "userId": user["id"], "role": "admin", "mfa": True, "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=Config.ADMIN_JWT_EXPIRY_HOURS),
    }, Config.SECRET_KEY, algorithm="HS256")
    return jsonify({"message": _("Two-step login is on"), "token": token}), 200


@admin_bp.route("/admin/two-step/reset/<int:user_id>", methods=["POST"])
def two_step_reset(user_id):
    """Another admin turns an admin's two-step login off (a lost phone); they set it up
    again at their next login."""
    admin, error = admin_or_error()
    if error:
        return error
    target = get_user_by_id(user_id)
    if not target or target["role"] != "admin":
        return jsonify({"message": _("User not found")}), 404
    if target["id"] == admin["userId"]:
        return jsonify({"message": _("Ask another admin to reset your two-step login")}), 400
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET totpEnabled = 0, totpSecret = NULL, totpLastStep = NULL WHERE id = ?",
                   (user_id,))
    conn.commit()
    conn.close()
    log_action(admin["userId"], "two_step_reset", user_id, ip_address=client_ip())
    return jsonify({"message": _("Two-step login was reset for this admin")}), 200
