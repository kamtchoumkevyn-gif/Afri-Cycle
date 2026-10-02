from database.db import get_connection


def set_price(buyer_id, material_category_id, price_per_kg):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM buyer_prices WHERE buyerId = ? AND materialCategoryId = ?",
        (buyer_id, material_category_id)
    )
    existing = cursor.fetchone()

    if existing:
        cursor.execute(
            "UPDATE buyer_prices SET pricePerKg = ? WHERE id = ?",
            (price_per_kg, existing["id"])
        )
        price_id = existing["id"]
    else:
        cursor.execute(
            "INSERT INTO buyer_prices (buyerId, materialCategoryId, pricePerKg) VALUES (?, ?, ?)",
            (buyer_id, material_category_id, price_per_kg)
        )
        price_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return price_id


def get_price_by_id(price_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM buyer_prices WHERE id = ?", (price_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_prices_by_buyer(buyer_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM buyer_prices WHERE buyerId = ?", (buyer_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_price_for_buyer_and_category(buyer_id, material_category_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM buyer_prices WHERE buyerId = ? AND materialCategoryId = ?",
        (buyer_id, material_category_id)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_price(price_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM buyer_prices WHERE id = ?", (price_id,))
    conn.commit()
    conn.close()
