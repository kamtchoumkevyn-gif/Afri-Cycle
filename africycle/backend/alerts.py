"""What the app tells people through phone notifications: new chat messages, and a
seller's trip to a buyer (coming, on the way, arrived). Sending is done by webpush.py;
people who haven't turned notifications on simply get nothing here (the app itself
still shows unread messages and trips when they open it). Each phone gets them in the
language chosen on it."""
import os

from flask import request

import webpush
from database.db import get_connection
from i18n import N_, _

TRIP_NEWS = {
    "pending": (N_("{seller} is coming to you"), N_("Material: {material}. Open Africycle to see the details.")),
    "in transit": (N_("{seller} is on the way"), N_("Material: {material}. Follow them on your map.")),
    "arrived": (N_("{seller} has arrived"), N_("Material: {material}. Weigh it, then record the purchase.")),
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
    name = sender["name"] if sender else "Africycle"
    webpush.notify_user(receiver_id, lambda language: {
        "title": _("Message from {name}", language, name=name),
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
    webpush.notify_user(trip["buyerId"], lambda language: {
        "title": _(title, language, seller=trip["sellerName"]),
        "body": _(body, language, material=_(trip["materialName"] or N_("Materials"), language)),
        "url": "/buyer-dashboard.html",
        "tag": f"trip-{notification_id}",
    }, push_subject())
