"""Database access for Africycle.

By default data lives in a SQLite file (local development and tests).
When the DATABASE_URL environment variable is set, for example to a free
Neon Postgres database in Render's Environment settings, the same code uses
Postgres instead, so accounts survive redeploys and restarts.

Models and routes keep writing SQLite-style SQL ("?" placeholders,
camelCase column names, cursor.lastrowid). PostgresConnection translates it,
so the rest of the app doesn't need to know which database is in use.
"""
import os
import re
import sqlite3

# Tests set AFRICYCLE_DB_PATH to a temporary file so they never touch real data
DB_PATH = os.environ.get(
    "AFRICYCLE_DB_PATH",
    os.path.join(os.path.dirname(__file__), "africycle.db")
)

# Listed in creation order (tables that others point to come first)
SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phoneNumber TEXT UNIQUE NOT NULL,
        passwordHash TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        isFlagged INTEGER DEFAULT 0,
        flagReason TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS material_category (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        referencePhotoUrl TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS buyer_profile (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        userId INTEGER NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        workingHours TEXT,
        FOREIGN KEY (userId) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS buyer_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        buyerId INTEGER NOT NULL,
        materialCategoryId INTEGER NOT NULL,
        pricePerKg REAL NOT NULL,
        FOREIGN KEY (buyerId) REFERENCES users(id),
        FOREIGN KEY (materialCategoryId) REFERENCES material_category(id)
    )
    """,
    """
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
    """,
    """
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
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        senderId INTEGER NOT NULL,
        receiverId INTEGER NOT NULL,
        messageText TEXT NOT NULL,
        createdAt TEXT NOT NULL,
        FOREIGN KEY (senderId) REFERENCES users(id),
        FOREIGN KEY (receiverId) REFERENCES users(id)
    )
    """,
]

TABLES = [re.search(r"EXISTS (\w+)", statement).group(1) for statement in SCHEMA]


def database_url():
    """The Postgres URL from the environment, or "" when the SQLite file should be used."""
    return os.environ.get("DATABASE_URL", "").strip()


def using_postgres():
    return bool(database_url())


def get_connection():
    if using_postgres():
        return PostgresConnection(database_url())
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    if using_postgres():
        # Several server processes may start at once; let one create the tables at a time
        cursor.execute(f"SELECT pg_advisory_xact_lock({_INIT_LOCK_ID})")
    for statement in SCHEMA:
        cursor.execute(statement)
    conn.commit()
    conn.close()


def reset_db():
    """Drops and recreates every table. Only the test suite calls this."""
    conn = get_connection()
    cursor = conn.cursor()
    for table in reversed(TABLES):
        cursor.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    conn.close()
    init_db()


# ---- Postgres support -------------------------------------------------------

_INIT_LOCK_ID = 46_210_001  # any fixed number; identifies init_db's lock
_STRING_LITERAL = re.compile(r"('(?:[^']|'')*')")
_CAMEL_CASE_NAME = re.compile(r'(?<![\w"])([a-z][a-z0-9]*[A-Z][A-Za-z0-9]*)(?![\w"])')
_INSERT = re.compile(r"^\s*INSERT\s+INTO\s", re.IGNORECASE)


def to_postgres(sql, has_params=True):
    """Rewrites the app's SQLite-style SQL so Postgres runs it the same way.

    - "?" placeholders become "%s" (and a literal "%" becomes "%%")
    - camelCase names get double quotes; otherwise Postgres would lowercase
      them and the API would return "phonenumber" instead of "phoneNumber"
    - SQLite-only column definitions become their Postgres equivalents
    Text inside single quotes ('pending', 'seller', ...) is left untouched.
    """
    parts = _STRING_LITERAL.split(sql)
    for i in range(0, len(parts), 2):  # even positions are outside quotes
        part = parts[i]
        if has_params:
            part = part.replace("%", "%%").replace("?", "%s")
        part = _CAMEL_CASE_NAME.sub(r'"\1"', part)
        part = re.sub(r"\bINTEGER PRIMARY KEY AUTOINCREMENT\b",
                      "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY", part)
        part = re.sub(r"\bREAL\b", "DOUBLE PRECISION", part)
        parts[i] = part
    return "".join(parts)


class PostgresCursor:
    """Behaves like the sqlite3 cursor for the calls the app makes."""

    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid = None

    def execute(self, sql, params=None):
        sql = to_postgres(sql, has_params=params is not None)
        wants_id = bool(_INSERT.match(sql)) and "RETURNING" not in sql.upper()
        if wants_id:
            # Postgres has no lastrowid; ask the INSERT to hand back the new id instead
            sql = sql.rstrip().rstrip(";") + " RETURNING id"
        self._cursor.execute(sql, params)
        if wants_id:
            row = self._cursor.fetchone()  # None when ON CONFLICT DO NOTHING skipped the row
            self.lastrowid = row["id"] if row else None
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount


class PostgresConnection:
    """Behaves like a sqlite3 connection for the calls the app makes."""

    def __init__(self, url):
        import psycopg  # only needed when DATABASE_URL is set
        from psycopg.rows import dict_row

        self._conn = psycopg.connect(url, row_factory=dict_row, connect_timeout=15)
        # Each request opens a fresh connection, and Neon's pooler doesn't keep
        # server-side prepared statements between them, so don't create any
        self._conn.prepare_threshold = None

    def cursor(self):
        return PostgresCursor(self._conn.cursor())

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
