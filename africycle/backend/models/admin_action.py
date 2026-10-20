"""The admin action log: who did what, to which account, and when.

Every admin login, wrong two-step code, flag, approval of a new admin, two-step
login change and voice recording change is written here. The admin page shows the
newest ones; nothing offers to edit or delete them.
"""
from datetime import datetime

from database.db import get_connection

ACTIONS = ("login", "wrong_code", "flag", "unflag", "admin_approved", "two_step_on", "two_step_reset",
           "recording_saved", "recording_deleted")


def log_action(admin_id, action, target_user_id=None, details=None, ip_address=None):
    assert action in ACTIONS, action
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO admin_actions (adminId, action, targetUserId, details, ipAddress, createdAt)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (admin_id, action, target_user_id, (details or "")[:300] or None, ip_address,
         datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def recent_actions(limit=200):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT a.id, a.action, a.details, a.ipAddress, a.createdAt,
               a.adminId, admin.name AS adminName,
               a.targetUserId, target.name AS targetName
        FROM admin_actions a
        LEFT JOIN users admin ON admin.id = a.adminId
        LEFT JOIN users target ON target.id = a.targetUserId
        ORDER BY a.id DESC
        LIMIT ?
        """,
        (limit,)
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows
