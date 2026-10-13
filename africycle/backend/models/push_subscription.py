from datetime import datetime

from database.db import get_connection


def save_subscription(user_id, endpoint, p256dh, auth_secret):
    """Stores a device that agreed to receive notifications. One device belongs to the
    account that last turned notifications on there (after a log out and log in as
    someone else, it moves to the new account)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO push_subscriptions (userId, endpoint, p256dh, authSecret, createdAt)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (endpoint) DO UPDATE SET
            userId = excluded.userId, p256dh = excluded.p256dh, authSecret = excluded.authSecret
        """,
        (user_id, endpoint, p256dh, auth_secret, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def delete_subscription(endpoint, user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    if user_id is None:
        cursor.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
    else:
        cursor.execute("DELETE FROM push_subscriptions WHERE endpoint = ? AND userId = ?", (endpoint, user_id))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def get_subscriptions_for_user(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT endpoint, p256dh, authSecret FROM push_subscriptions WHERE userId = ?", (user_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows
