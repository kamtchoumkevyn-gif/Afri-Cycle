from database.db import get_connection


def create_buyer_profile(user_id, latitude, longitude, working_hours=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO buyer_profile (userId, latitude, longitude, workingHours) VALUES (?, ?, ?, ?)",
        (user_id, latitude, longitude, working_hours)
    )
    conn.commit()
    profile_id = cursor.lastrowid
    conn.close()
    return profile_id


def get_buyer_profile_by_user_id(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM buyer_profile WHERE userId = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_buyer_location(user_id, latitude, longitude):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE buyer_profile SET latitude = ?, longitude = ? WHERE userId = ?",
        (latitude, longitude, user_id)
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def update_working_hours(user_id, working_hours):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE buyer_profile SET workingHours = ? WHERE userId = ?",
        (working_hours, user_id)
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def delete_buyer_profile(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM buyer_profile WHERE userId = ?", (user_id,))
    conn.commit()
    conn.close()
