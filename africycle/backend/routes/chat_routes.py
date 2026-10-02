from flask import Blueprint, request, jsonify
from auth_utils import get_user_from_token
from database.db import get_connection
from models.chat import send_message, get_conversation, get_conversations_for_user

chat_bp = Blueprint("chat_bp", __name__)


@chat_bp.route("/chat/conversations", methods=["GET"])
def conversations():
    payload = get_user_from_token()
    if not payload:
        return jsonify({"message": "Unauthorized"}), 401

    convos = get_conversations_for_user(payload["userId"])

    conn = get_connection()
    cursor = conn.cursor()
    for convo in convos:
        cursor.execute("SELECT name FROM users WHERE id = ?", (convo["otherUserId"],))
        row = cursor.fetchone()
        convo["otherUserName"] = row["name"] if row else None
    conn.close()

    return jsonify({"conversations": convos}), 200


@chat_bp.route("/chat/messages/<int:other_user_id>", methods=["GET"])
def messages(other_user_id):
    payload = get_user_from_token()
    if not payload:
        return jsonify({"message": "Unauthorized"}), 401

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE id = ?", (other_user_id,))
    other = cursor.fetchone()
    conn.close()

    if not other:
        return jsonify({"message": "User not found"}), 404

    thread = get_conversation(payload["userId"], other_user_id)
    return jsonify({"otherUserName": other["name"], "messages": thread}), 200


@chat_bp.route("/chat/send", methods=["POST"])
def send():
    payload = get_user_from_token()
    if not payload:
        return jsonify({"message": "Unauthorized"}), 401

    data = request.get_json() or {}
    receiver_id = data.get("receiverId")
    message_text = (data.get("messageText") or "").strip()

    if not receiver_id or not message_text:
        return jsonify({"message": "receiverId and messageText are required"}), 400

    if len(message_text) > 1000:
        return jsonify({"message": "Message is too long (max 1000 characters)"}), 400

    if receiver_id == payload["userId"]:
        return jsonify({"message": "You cannot message yourself"}), 400

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE id = ?", (receiver_id,))
    exists = cursor.fetchone()
    conn.close()
    if not exists:
        return jsonify({"message": "Receiver not found"}), 404

    message_id = send_message(payload["userId"], receiver_id, message_text)
    return jsonify({"message": "Sent", "messageId": message_id}), 201
