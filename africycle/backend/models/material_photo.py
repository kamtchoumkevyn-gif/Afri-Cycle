"""Reference photos buyers upload for each material they buy.

Images live in the database (base64 text) because Render's free disk is wiped on
every restart. The client shrinks them first, so each is a few hundred KB at most.
"""
from datetime import datetime
from database.db import get_connection


def save_photo(buyer_id, material_category_id, mime_type, image_base64):
    """Replaces the buyer's photo for this material. A new id each time means
    browsers never show an old cached image."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM material_photos WHERE buyerId = ? AND materialCategoryId = ?",
        (buyer_id, material_category_id)
    )
    cursor.execute(
        """
        INSERT INTO material_photos (buyerId, materialCategoryId, mimeType, imageData, createdAt)
        VALUES (?, ?, ?, ?, ?)
        """,
        (buyer_id, material_category_id, mime_type, image_base64, datetime.utcnow().isoformat())
    )
    photo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return photo_id


def get_photo(photo_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM material_photos WHERE id = ?", (photo_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_photo(buyer_id, material_category_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM material_photos WHERE buyerId = ? AND materialCategoryId = ?",
        (buyer_id, material_category_id)
    )
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted
