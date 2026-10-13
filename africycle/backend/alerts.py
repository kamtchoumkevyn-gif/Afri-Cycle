"""What the app tells people through phone notifications: new chat messages, and a
seller's trip to a buyer (coming, on the way, arrived). Sending is done by webpush.py;
people who haven't turned notifications on simply get nothing here (the app itself
still shows unread messages and trips when they open it)."""
import os

from flask import request

import webpush
from database.db import get_connection

TRIP_NEWS = {
    "pending": ("{seller} is bringing you {material}", "Open Africycle to see the details."),
    "in transit": ("{seller} is on the way", "Bringing {material}. Follow them on your map."),
    "arrived": ("{seller} has arrived", "With {material}. Weigh it, then record the purchase."),
}


def push_subject():
    """Who the notifications come from (the VAPID "sub"): this site's address."""
    configured = os.environ.get("VAPID_SUBJECT")
    if configured:
        return configured
    if request.host.split(":")[0] in ("localhost", "127.0.0.1"):
        return request.url_root.rstrip("/")
    return f"https://{request.host}"  # Render serves the site over HTTPS


def new_message(sender_id, receiver_id, text):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE id = ?", (sender_id,))
    sender = cursor.fetchone()
    conn.close()
    webpush.notify_user(receiver_id, {
        "title": f"Message from {sender['name'] if sender else 'Africycle'}",
        "body": webpush.short(text),
        "url": f"/chat.html?with={sender_id}",
        "tag": f"chat-{sender_id}",  # several messages from one person stay one notification
    }, push_subject())


def trip_update(notification_id, status):
    if status not in TRIP_NEWS:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT n.buyerId, s.name AS sellerName, m.name AS materialName
        FROM notifications n
        JOIN users s ON s.id = n.sellerId
        LEFT JOIN material_category m ON m.id = n.materialCategoryId
        WHERE n.id = ?
        """,
        (notification_id,)
    )
    trip = cursor.fetchone()
    conn.close()
    if not trip:
        return
    title, body = TRIP_NEWS[status]
    words = {"seller": trip["sellerName"], "material": (trip["materialName"] or "materials").lower()}
    webpush.notify_user(trip["buyerId"], {
        "title": title.format(**words),
        "body": body.format(**words),
        "url": "/buyer-dashboard.html",
        "tag": f"trip-{notification_id}",
    }, push_subject())
