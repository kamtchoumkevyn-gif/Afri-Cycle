from datetime import datetime
from database.db import get_connection


def create_transaction(seller_id, buyer_id, material_category_id, weight_kg, price_per_kg, photo_url=None):
    total_amount = weight_kg * price_per_kg
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO transactions
            (sellerId, buyerId, materialCategoryId, weightKg, pricePerKg, totalAmount, photoUrl, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            seller_id, buyer_id, material_category_id,
            weight_kg, price_per_kg, total_amount, photo_url,
            datetime.utcnow().isoformat()
        )
    )
    conn.commit()
    transaction_id = cursor.lastrowid
    conn.close()
    return transaction_id


def get_transaction_by_id(transaction_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_transactions_by_buyer(buyer_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM transactions WHERE buyerId = ? ORDER BY createdAt DESC",
        (buyer_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_transactions_by_seller(seller_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM transactions WHERE sellerId = ? ORDER BY createdAt DESC",
        (seller_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
