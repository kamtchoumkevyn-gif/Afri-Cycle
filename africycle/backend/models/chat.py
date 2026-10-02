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


def delete_message(message_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_messages WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
