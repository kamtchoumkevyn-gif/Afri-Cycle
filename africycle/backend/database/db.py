import sqlite3
import os

# Tests set AFRICYCLE_DB_PATH to a temporary file so they never touch real data
DB_PATH = os.environ.get(
    "AFRICYCLE_DB_PATH",
    os.path.join(os.path.dirname(__file__), "africycle.db")
)


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phoneNumber TEXT UNIQUE NOT NULL,
            passwordHash TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            isFlagged INTEGER DEFAULT 0,
            flagReason TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS material_category (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            referencePhotoUrl TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS buyer_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            userId INTEGER NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            workingHours TEXT,
            FOREIGN KEY (userId) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS buyer_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyerId INTEGER NOT NULL,
            materialCategoryId INTEGER NOT NULL,
            pricePerKg REAL NOT NULL,
            FOREIGN KEY (buyerId) REFERENCES users(id),
            FOREIGN KEY (materialCategoryId) REFERENCES material_category(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sellerId INTEGER NOT NULL,
            buyerId INTEGER NOT NULL,
            materialCategoryId INTEGER NOT NULL,
            weightKg REAL NOT NULL,
            pricePerKg REAL NOT NULL,
            totalAmount REAL NOT NULL,
            photoUrl TEXT,
            createdAt TEXT NOT NULL,
            FOREIGN KEY (sellerId) REFERENCES users(id),
            FOREIGN KEY (buyerId) REFERENCES users(id),
            FOREIGN KEY (materialCategoryId) REFERENCES material_category(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sellerId INTEGER NOT NULL,
            buyerId INTEGER NOT NULL,
            materialCategoryId INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            sellerLatitude REAL,
            sellerLongitude REAL,
            createdAt TEXT NOT NULL,
            FOREIGN KEY (sellerId) REFERENCES users(id),
            FOREIGN KEY (buyerId) REFERENCES users(id),
            FOREIGN KEY (materialCategoryId) REFERENCES material_category(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            senderId INTEGER NOT NULL,
            receiverId INTEGER NOT NULL,
            messageText TEXT NOT NULL,
            createdAt TEXT NOT NULL,
            FOREIGN KEY (senderId) REFERENCES users(id),
            FOREIGN KEY (receiverId) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
