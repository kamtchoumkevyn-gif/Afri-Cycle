from datetime import datetime
from database.db import get_connection


def send_message(sender_id, receiver_id, message_text):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO chat_messages (senderId, receiverId, messageText, createdAt)
        VALUES (?, ?, ?, ?)
        """,
        (sender_id, receiver_id, message_text, datetime.utcnow().isoformat())
    )
    conn.commit()
    message_id = cursor.lastrowid
    conn.close()
    return message_id


def get_message_by_id(message_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_conversation(user_a_id, user_b_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM chat_messages
        WHERE (senderId = ? AND receiverId = ?)
           OR (senderId = ? AND receiverId = ?)
        ORDER BY createdAt ASC
        """,
        (user_a_id, user_b_id, user_b_id, user_a_id)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_conversations_for_user(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT
            CASE WHEN senderId = ? THEN receiverId ELSE senderId END AS otherUserId,
            MAX(createdAt) AS lastMessageAt
        FROM chat_messages
        WHERE senderId = ? OR receiverId = ?
        GROUP BY otherUserId
        ORDER BY lastMessageAt DESC
        """,
        (user_id, user_id, user_id)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_conversation_read(reader_id, other_user_id):
    """Marks everything other_user_id sent to reader_id as read."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE chat_messages SET readAt = ? WHERE receiverId = ? AND senderId = ? AND readAt IS NULL",
        (datetime.utcnow().isoformat(), reader_id, other_user_id)
    )
    conn.commit()
    conn.close()


def unread_summary(user_id):
    """How many messages user_id hasn't read, per sender, and the newest one."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT senderId, COUNT(*) AS unread FROM chat_messages "
        "WHERE receiverId = ? AND readAt IS NULL GROUP BY senderId",
        (user_id,)
    )
    by_sender = {str(row["senderId"]): row["unread"] for row in cursor.fetchall()}
    cursor.execute(
        """
        SELECT m.id, m.senderId, u.name AS senderName, m.messageText, m.createdAt
        FROM chat_messages m JOIN users u ON u.id = m.senderId
        WHERE m.receiverId = ? AND m.readAt IS NULL
        ORDER BY m.id DESC LIMIT 1
        """,
        (user_id,)
    )
    latest = cursor.fetchone()
    conn.close()
    return {"unread": sum(by_sender.values()), "bySender": by_sender,
            "latest": dict(latest) if latest else None}


def delete_message(message_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_messages WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
