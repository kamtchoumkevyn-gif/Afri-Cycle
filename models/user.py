import sys
import os
import bcrypt
import datetime
import sqlite3
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.db import get_connection


def hash_password(plain_password):
    """"Hash a plain text password using bcrypt."""
    password_bytes = plain_password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def check_password(plain_password,hashed_password):
    """"Checks a plain text password against a stored hash."""
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode('utf-8')
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password)    
   
   
    
def create_user(phone_number, password, role, guardian_phone_number=None):
    """"Create a new user (seller or buyer) in the database."""
    
    conn = get_connection()
    cursor = conn.cursor()
    
    password_hash = hash_password(password)
    created_at = datetime.datetime.now().isoformat()
    
    try:
        cursor.execute('''
            INSERT INTO users (phoneNumber, passwordHash, role, guardianPhoneNumber, verified, createdAt)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (phone_number, password_hash, role, guardian_phone_number, False, created_at))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except Exception as e:
        conn.close()
        raise e
    
def find_user_by_phone(phone_number):
    """Fetch a single user record by phone number."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE phoneNumber = ?", (phone_number,))
    user = cursor.fetchone()
    conn.close()
    return user
   
def verify_login(phone_number, password):
    """"Checks phone number + password combo. Returns the user if valid, None if not."""
    user = find_user_by_phone(phone_number)
    if user is None:
        return None
    if check_password(password, user['passwordHash']):
        return user
    return None        
    