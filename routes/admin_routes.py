"""
Admin routes:user counts/activity stats + flagging suspicious accounts.

ASSUMPTION TO VERIFY: this reads a "users" JSON collection with fields matching the User class in the diagram (phoneNumber, role, verified,createAt). If the teammate's user.py stores users differently (a DB table, a different JSON shape  etc.), swap 'read_all("users)' below for whatever function they expose (eg. 'get-all_users()'), and adjust the field names to match. Everything else (route paths, response shape) can stay the same.
"""
from flask import Blueprint, request, jsonify
from collections import Counter

from utils.storage import read_all, write_all
from routes.notification_routes import require_auth

admin_bp = Blueprint("admin_bp", __name__)

USERS_COLLECTION = "users"


def require_admin(f):
    """Wraps require_auth with a role check. Assumes the JWT payload has a 'role' claim."""
    @require_auth
    def wrapper(*args, **kwargs):
        if request.user.get("role") != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


@admin_bp.route("/admin/stats", methods=["GET"])
@require_admin
def get_stats():
    users = read_all(USERS_COLLECTION)
    notifications = read_all("notifications")
    
    role_counts = Counter(u.get("role", "unknown") for u in users)
    status_counts = Counter(n.get("status", "unknown") for n in notifications)
    
    stats = {
        "totalUsers": len(users),
        "userByRole": dict(role_counts),
        "verifiedUsers": sum(1 for u in users if u.get("verified")),
        "flaggedUsers": sum(1 for u in users if u.get("flagged")),
        "totalNotifications": len(notifications),
        "notificationsByStatus": dict(status_counts), 
    }
    return jsonify(stats), 200


@admin_bp.route("/admin/users", methods=["GET"])
@require_admin
def list_users():
    users = read_all(USERS_COLLECTION)
    role_filter = request.args.get("role")
    flagged_only = request.args.get("flagged") == "true"
    
    if role_filter:
        users = [u for u in users if u.get("role") == role_filter]
    if flagged_only:
        users = [u for u in users if u.get("flagged")]
        
    safe_users = [{k: v for k, v in u.items() if k != "passwordHash"} for u in users]
    return jsonify(safe_users), 200

@admin_bp.route("/admin/users/<phone_number>/flag", methods=["PATCH"])
@require_admin
def flag_user(phone_number):
    data = request.get_json(silent=True) or {}
    flagged = data.get("flagged", True)
    reason = data.get("reason")    
    
    users = read_all(USERS_COLLECTION)
    target = next((u for u in users if u.get("phoneNumber") ==phone_number), None)
    if target is None:
        return jsonify({"error": "User not found"}), 404
    
    target["flagged"] = flagged
    target["flagReason"] = reason if flagged else None
    write_all(USERS_COLLECTION, users)
    
    return jsonify({"success": True, "phoneNumber": phone_number, "flagged": flagged}), 200
    