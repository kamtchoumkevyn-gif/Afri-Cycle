from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from auth_utils import get_user_from_token
from database.db import get_connection

admin_bp = Blueprint("admin_bp", __name__)


def require_admin():
    payload = get_user_from_token()
    if not payload or payload.get("role") != "admin":
        return None
    return payload


def count(cursor, query, params=()):
    cursor.execute(query, params)
    return cursor.fetchone()["count"]


@admin_bp.route("/admin/stats", methods=["GET"])
def user_counts():
    if not require_admin():
        return jsonify({"message": "Unauthorized"}), 401

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
    if not require_admin():
        return jsonify({"message": "Unauthorized"}), 401

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
        GROUP BY t.materialCategoryId
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
    if not require_admin():
        return jsonify({"message": "Unauthorized"}), 401

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id AS userId, name, phoneNumber, role, isFlagged, flagReason FROM users ORDER BY id DESC"
    )
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"users": users}), 200


@admin_bp.route("/admin/flagged-accounts", methods=["GET"])
def flagged_accounts():
    if not require_admin():
        return jsonify({"message": "Unauthorized"}), 401

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
    if not require_admin():
        return jsonify({"message": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    reason = data.get("reason") or "Flagged by admin"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET isFlagged = 1, flagReason = ? WHERE id = ?", (reason, user_id)
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()

    if not updated:
        return jsonify({"message": "User not found"}), 404
    return jsonify({"message": "Account flagged"}), 200


@admin_bp.route("/admin/unflag-account/<int:user_id>", methods=["POST"])
def unflag_account(user_id):
    if not require_admin():
        return jsonify({"message": "Unauthorized"}), 401

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET isFlagged = 0, flagReason = NULL WHERE id = ?", (user_id,)
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()

    if not updated:
        return jsonify({"message": "User not found"}), 404
    return jsonify({"message": "Account unflagged"}), 200
