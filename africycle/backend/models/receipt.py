"""Receipts: the purchases buyers record (the transactions table), with photos of the
material that was bought.

A receipt can have up to MAX_PHOTOS photos, taken by the buyer when recording the
purchase or added later. Like material photos, they are kept in the database (base64
text) because Render's free disk is wiped on every restart; the page shrinks each one
to a couple of hundred KB first.
"""
from datetime import datetime

from database.db import get_connection

MAX_PHOTOS = 3

# Number of photos on each receipt, for the lists of purchases and sales
PHOTO_COUNT = "(SELECT COUNT(*) FROM transaction_photos p WHERE p.transactionId = t.id) AS photoCount"


def get_receipt(transaction_id):
    """The purchase with the names of both sides and of the material, or None."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT t.id, t.sellerId, t.buyerId, t.materialCategoryId, t.weightKg, t.pricePerKg,
               t.totalAmount, t.createdAt,
               s.name AS sellerName, b.name AS buyerName, m.name AS materialName
        FROM transactions t
        LEFT JOIN users s ON s.id = t.sellerId
        LEFT JOIN users b ON b.id = t.buyerId
        LEFT JOIN material_category m ON m.id = t.materialCategoryId
        WHERE t.id = ?
        """,
        (transaction_id,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    receipt = dict(row)
    cursor.execute(
        "SELECT id FROM transaction_photos WHERE transactionId = ? ORDER BY id",
        (transaction_id,)
    )
    receipt["photoIds"] = [photo["id"] for photo in cursor.fetchall()]
    conn.close()
    return receipt


def count_photos(transaction_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS count FROM transaction_photos WHERE transactionId = ?",
                   (transaction_id,))
    count = cursor.fetchone()["count"]
    conn.close()
    return count


def add_photo(transaction_id, mime_type, image_base64):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO transaction_photos (transactionId, mimeType, imageData, createdAt)
        VALUES (?, ?, ?, ?)
        """,
        (transaction_id, mime_type, image_base64, datetime.utcnow().isoformat())
    )
    photo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return photo_id


def get_photo(photo_id):
    """The photo with the id of its receipt, or None."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transaction_photos WHERE id = ?", (photo_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_photo(transaction_id, photo_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transaction_photos WHERE id = ? AND transactionId = ?",
                   (photo_id, transaction_id))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def sales_of(seller_id):
    """The purchases buyers recorded with this seller, newest first."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT t.*, b.name AS buyerName, m.name AS materialName, {PHOTO_COUNT}
        FROM transactions t
        JOIN users b ON b.id = t.buyerId
        LEFT JOIN material_category m ON m.id = t.materialCategoryId
        WHERE t.sellerId = ?
        ORDER BY t.createdAt DESC
        """,
        (seller_id,)
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows
