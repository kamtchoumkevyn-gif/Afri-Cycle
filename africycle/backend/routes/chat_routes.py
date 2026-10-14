from flask import Blueprint, request, jsonify
from i18n import _

import alerts
from auth_utils import get_user_from_token, guardian_block
from database.db import get_connection
from models.chat import (get_conversation, get_conversations_for_user, mark_conversation_read,
                         send_message, unread_summary)

chat_bp = Blueprint("chat_bp", __name__)


@chat_bp.route("/chat/conversations", methods=["GET"])
def conversations():
    payload = get_user_from_token()
    if not payload:
        return jsonify({"message": _("Unauthorized")}), 401

    convos = get_conversations_for_user(payload["userId"])
    unread = unread_summary(payload["userId"])["bySender"]

    conn = get_connection()
    cursor = conn.cursor()
    for convo in convos:
        cursor.execute("SELECT name FROM users WHERE id = ?", (convo["otherUserId"],))
        row = cursor.fetchone()
        convo["otherUserName"] = row["name"] if row else None
        convo["unread"] = unread.get(str(convo["otherUserId"]), 0)
    conn.close()

    return jsonify({"conversations": convos}), 200


@chat_bp.route("/chat/unread", methods=["GET"])
def unread():
    """Unread messages for the badge on "Messages", and the newest one for a pop-up."""
    payload = get_user_from_token()
    if not payload:
        return jsonify({"message": _("Unauthorized")}), 401
    return jsonify(unread_summary(payload["userId"])), 200


@chat_bp.route("/chat/messages/<int:other_user_id>", methods=["GET"])
def messages(other_user_id):
    payload = get_user_from_token()
    if not payload:
        return jsonify({"message": _("Unauthorized")}), 401

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, isMinor FROM users WHERE id = ?", (other_user_id,))
    other = cursor.fetchone()
    conn.close()

    if not other:
        return jsonify({"message": _("User not found")}), 404

    # Opening the conversation reads it; ?read=0 is sent while the page is in the background
    if request.args.get("read") != "0":
        mark_conversation_read(payload["userId"], other_user_id)

    thread = get_conversation(payload["userId"], other_user_id)
    # Under-18 sellers' guardians can read their conversations; the page says so
    return jsonify({"otherUserName": other["name"], "otherIsMinor": bool(other["isMinor"]),
                    "messages": thread}), 200


@chat_bp.route("/chat/send", methods=["POST"])
def send():
    payload = get_user_from_token()
    if not payload:
        return jsonify({"message": _("Unauthorized")}), 401

    data = request.get_json() or {}
    receiver_id = data.get("receiverId")
    message_text = (data.get("messageText") or "").strip()

    if not receiver_id or not message_text:
        return jsonify({"message": "receiverId and messageText are required"}), 400

    if len(message_text) > 1000:
        return jsonify({"message": _("Message is too long (max 1000 characters)")}), 400

    if receiver_id == payload["userId"]:
        return jsonify({"message": _("You cannot message yourself")}), 400

    blocked = guardian_block(payload["userId"])
    if blocked:
        return blocked

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE id = ?", (receiver_id,))
    exists = cursor.fetchone()
    conn.close()
    if not exists:
        return jsonify({"message": _("Receiver not found")}), 404

    message_id = send_message(payload["userId"], receiver_id, message_text)
    # Replying means the sender has read what came before
    mark_conversation_read(payload["userId"], receiver_id)
    alerts.new_message(payload["userId"], receiver_id, message_text)
    return jsonify({"message": _("Sent"), "messageId": message_id}), 201
