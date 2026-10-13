import bcrypt
from database.db import get_connection


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_user(phone_number, password, name, role, guardian=None):
    """guardian: for a child's account, a dict with the guardian's name, phone and
    relation. Such an account can't trade until that guardian approves it."""
    password_hash = hash_password(password)
    conn = get_connection()
    cursor = conn.cursor()
    if guardian:
        cursor.execute(
            """
            INSERT INTO users (phoneNumber, passwordHash, name, role, isMinor,
                               guardianName, guardianPhone, guardianRelation, guardianStatus)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?, 'pending')
            """,
            (phone_number, password_hash, name, role,
             guardian["name"], guardian["phone"], guardian["relation"])
        )
    else:
        cursor.execute(
            "INSERT INTO users (phoneNumber, passwordHash, name, role) VALUES (?, ?, ?, ?)",
            (phone_number, password_hash, name, role)
        )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return user_id


def get_user_by_id(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def find_user_by_phone(phone_number):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE phoneNumber = ?", (phone_number,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def find_users_by_phones(phone_numbers):
    """The accounts saved under any of these numbers, in the order the numbers are given
    (one query, however many numbers)."""
    phone_numbers = list(phone_numbers)
    if not phone_numbers:
        return []
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ", ".join("?" for _ in phone_numbers)
    cursor.execute(f"SELECT * FROM users WHERE phoneNumber IN ({placeholders})", tuple(phone_numbers))
    found = {row["phoneNumber"]: dict(row) for row in cursor.fetchall()}
    conn.close()
    return [found[number] for number in phone_numbers if number in found]


def verify_login(phone_number, password):
    user = find_user_by_phone(phone_number)
    if not user:
        return None
    if not check_password(password, user["passwordHash"]):
        return None
    return user
