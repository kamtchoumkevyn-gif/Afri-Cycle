import bcrypt
from database.db import get_connection


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_user(phone_number, password, name, role):
    password_hash = hash_password(password)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (phoneNumber, passwordHash, name, role) VALUES (?, ?, ?, ?)",
        (phone_number, password_hash, name, role)
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return user_id


def find_user_by_phone(phone_number):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE phoneNumber = ?", (phone_number,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def verify_login(phone_number, password):
    user = find_user_by_phone(phone_number)
    if not user:
        return None
    if not check_password(password, user["passwordHash"]):
        return None
    return user
