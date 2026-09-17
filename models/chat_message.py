"""
ChatMessage model - matches the ChatMessage class in the diagram : notification, senderId, messageText, timestamp + sendMessage(notificationId, senderId, messageText): boolean
"""
from datetime import datetime
from utils.storage import read_all, write_all, next_id
from models.notification import get_notification_by_id

COLLECTION = "chat_messages"

def send_message(notification_id: int, sender_id: str, message_text: str) -> dict | None:
    """
    Creates a chat message tied to a notification thread.
    Returns the created message dict, or None if the notification doesn't exist or the message text is empty.
    """
    if not message_text or not message_text.strip():
        return None
    
    notification = get_notification_by_id(notification_id)
    if notification is None:
        return None
    
    records = read_all(COLLECTION)
    message = {
        "id": next_id(records),
        "notificationId": notification_id,
        "senderId": sender_id,
        "messageText": message_text.strip(),
        "timestamp": datetime.utcnow().isoformat(),
    }
    records.append(message)
    write_all(COLLECTION, records)
    return message

def get_messages_for_notification(notification_id: int) -> list:
    records = read_all(COLLECTION)
    messages = [m for m in records if m["notificationId"] == notification_id]
    return sorted(messages, key=lambda m: m["timestamp"])