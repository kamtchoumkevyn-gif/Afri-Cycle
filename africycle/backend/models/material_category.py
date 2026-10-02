from database.db import get_connection


def create_material_category(name, reference_photo_url=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO material_category (name, referencePhotoUrl) VALUES (?, ?)",
        (name, reference_photo_url)
    )
    conn.commit()
    category_id = cursor.lastrowid
    conn.close()
    return category_id


def get_category_by_id(category_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM material_category WHERE id = ?", (category_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_category_by_name(name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM material_category WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_categories():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM material_category ORDER BY name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_reference_photo(category_id, reference_photo_url):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE material_category SET referencePhotoUrl = ? WHERE id = ?",
        (reference_photo_url, category_id)
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def delete_category(category_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM material_category WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()


def seed_default_categories():
    """Populates starter categories if the table is empty, so dropdowns have real data."""
    existing = get_all_categories()
    if existing:
        return
    defaults = [
        ("Scrap Iron", None),
        ("Plastic", None),
        ("Water Bidon", None),
        ("Organic Waste", None),
    ]
    for name, photo in defaults:
        create_material_category(name, photo)
