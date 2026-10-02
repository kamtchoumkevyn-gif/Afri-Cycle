from datetime import datetime
from database.db import get_connection

VALID_STATUSES = ["pending", "in transit", "arrived", "completed"]


def create_notification(seller_id, buyer_id, material_category_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO notifications
            (sellerId, buyerId, materialCategoryId, status, createdAt)
        VALUES (?, ?, ?, ?, ?)
        """,
        (seller_id, buyer_id, material_category_id, "pending", datetime.utcnow().isoformat())
    )
    conn.commit()
    notification_id = cursor.lastrowid
    conn.close()
    return notification_id


def get_notification_by_id(notification_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notifications WHERE id = ?", (notification_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_notifications_for_buyer(buyer_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM notifications WHERE buyerId = ? ORDER BY createdAt DESC",
        (buyer_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_notifications_for_seller(seller_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM notifications WHERE sellerId = ? ORDER BY createdAt DESC",
        (seller_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_location(notification_id, latitude, longitude):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE notifications SET sellerLatitude = ?, sellerLongitude = ? WHERE id = ?",
        (latitude, longitude, notification_id)
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def update_status(notification_id, new_status):
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {new_status}. Must be one of {VALID_STATUSES}")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE notifications SET status = ? WHERE id = ?",
        (new_status, notification_id)
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def delete_notification(notification_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))
    conn.commit()
    conn.close()
