import secrets

import bcrypt
from database.db import get_connection

# Wrong approval codes a guardian may type before the child needs a new code
APPROVAL_CODE_TRIES = 5


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def new_approval_code():
    """6 digits, shown on a child's phone, that the guardian types to approve the child."""
    return f"{secrets.randbelow(1_000_000):06d}"


def create_user(phone_number, password, name, role, guardian=None):
    """guardian: for a child's account, a dict with the guardian's name, phone and
    relation, and optionally the approval "code". Such an account can't trade until
    that guardian approves it with the code."""
    password_hash = hash_password(password)
    conn = get_connection()
    cursor = conn.cursor()
    if guardian:
        cursor.execute(
            """
            INSERT INTO users (phoneNumber, passwordHash, name, role, isMinor,
                               guardianName, guardianPhone, guardianRelation, guardianStatus,
                               approvalCode)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?, 'pending', ?)
            """,
            (phone_number, password_hash, name, role,
             guardian["name"], guardian["phone"], guardian["relation"], guardian.get("code"))
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


def approved_admin_exists():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE role = 'admin' AND adminApproved = 1 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row is not None


def approve_admin(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET adminApproved = 1 WHERE id = ? AND role = 'admin'", (user_id,))
    conn.commit()
    conn.close()


def set_approval_code(user_id, code, tries=0):
    """A child's approval code (None: none until the child asks for a new one)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET approvalCode = ?, approvalCodeTries = ? WHERE id = ?",
                   (code, tries, user_id))
    conn.commit()
    conn.close()


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
