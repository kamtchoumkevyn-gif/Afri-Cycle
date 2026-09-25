
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


# ============================================================
# CONFIGURATION
# ============================================================

class Config:
    DATABASE = "recycling_marketplace.db"
    HOST = "127.0.0.1"
    PORT = 5000
    SESSION_SECRET = os.getenv(
        "SESSION_SECRET",
        "dev-secret-change-this"
    )


# ============================================================
# DATABASE
# ============================================================

class Database:
    """SQLite database used by all UML model classes."""

    def __init__(self, database_path=Config.DATABASE):
        self.database_path = database_path
        self.initialize()

    def connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self):
        connection = self.connect()
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                verified INTEGER NOT NULL DEFAULT 0,
                role TEXT NOT NULL,
                phone_number TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                guardian_phone_number TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS buyer_profiles (
                user_id TEXT PRIMARY KEY,
                working_hours TEXT NOT NULL DEFAULT '08:00-18:00',
                latitude REAL NOT NULL DEFAULT 0.0,
                longitude REAL NOT NULL DEFAULT 0.0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS material_categories (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT NOT NULL,
                reference_photo_url TEXT NOT NULL DEFAULT ''
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS buyer_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_category_id TEXT NOT NULL,
                buyer_id TEXT NOT NULL,
                price_per_kilo REAL NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(material_category_id, buyer_id),
                FOREIGN KEY (material_category_id)
                    REFERENCES material_categories(id),
                FOREIGN KEY (buyer_id)
                    REFERENCES users(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                buyer_id TEXT NOT NULL,
                seller_phone_number TEXT NOT NULL,
                seller_name TEXT NOT NULL,
                material_category_id TEXT NOT NULL,
                weight_kg REAL NOT NULL,
                price_per_kilo REAL NOT NULL,
                photo_url TEXT NOT NULL DEFAULT '',
                latitude REAL NOT NULL DEFAULT 0.0,
                longitude REAL NOT NULL DEFAULT 0.0,
                confirmed_by_seller INTEGER NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (buyer_id) REFERENCES users(id),
                FOREIGN KEY (material_category_id)
                    REFERENCES material_categories(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                seller_id TEXT NOT NULL,
                buyer_id TEXT NOT NULL,
                material_category_id TEXT NOT NULL,
                seller_latitude REAL NOT NULL DEFAULT 0.0,
                seller_longitude REAL NOT NULL DEFAULT 0.0,
                estimated_distance_km REAL NOT NULL DEFAULT 0.0,
                estimated_time TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'unread',
                created_at TEXT NOT NULL,
                FOREIGN KEY (buyer_id) REFERENCES users(id),
                FOREIGN KEY (material_category_id)
                    REFERENCES material_categories(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notification_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                message_text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (notification_id)
                    REFERENCES notifications(id)
            )
        """)

        connection.commit()
        connection.close()

        self.seed_material_categories()

    def seed_material_categories(self):
        categories = [
            (
                "plastic",
                "Plastic",
                "Plastic bottles and other recyclable plastic.",
                ""
            ),
            (
                "metal",
                "Metal",
                "Ferrous and non-ferrous recyclable metal.",
                ""
            ),
            (
                "aluminium",
                "Aluminium",
                "Aluminium cans and aluminium scrap.",
                ""
            ),
            (
                "glass",
                "Glass",
                "Glass bottles and recyclable glass.",
                ""
            )
        ]

        connection = self.connect()
        connection.executemany(
            """
            INSERT OR IGNORE INTO material_categories
            (id, name, description, reference_photo_url)
            VALUES (?, ?, ?, ?)
            """,
            categories
        )
        connection.commit()
        connection.close()


# ============================================================
# HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize_phone(phone):
    return str(phone).strip()


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000
    ).hex()
    return f"pbkdf2_sha256$120000${salt}${digest}"


def verify_password(password, stored_hash):
    try:
        algorithm, rounds, salt, expected = stored_hash.split("$", 3)

        if algorithm != "pbkdf2_sha256":
            return False

        calculated = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(rounds)
        ).hex()

        return hmac.compare_digest(calculated, expected)
    except (ValueError, TypeError):
        return False


def safe_float(value, field_name):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number.")

    if result != result:
        raise ValueError(f"{field_name} must be a valid number.")

    return result


def distance_km(lat1, lon1, lat2, lon2):
    """Simple equirectangular approximation for short local distances."""
    import math

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)
    lon1 = math.radians(lon1)
    lon2 = math.radians(lon2)

    x = (lon2 - lon1) * math.cos((lat1 + lat2) / 2)
    y = lat2 - lat1

    earth_radius_km = 6371.0
    return earth_radius_km * math.sqrt(x * x + y * y)


# ============================================================
# USER
# UML:
# verified:boolean
# role:string
# phoneNumber:string
# passwordHash:string
# guardianPhoneNumber:string
# createdAt:string
# register(...)
# login(...)
# notifyBuyer(...)
# ============================================================

class User:
    """Base UML User class."""

    def __init__(
        self,
        user_id,
        verified,
        role,
        phone_number,
        password_hash,
        guardian_phone_number,
        created_at
    ):
        self.user_id = user_id
        self.verified = bool(verified)
        self.role = role
        self.phone_number = phone_number
        self.password_hash = password_hash
        self.guardian_phone_number = guardian_phone_number
        self.created_at = created_at

    def to_dict(self):
        return {
            "userId": self.user_id,
            "verified": self.verified,
            "role": self.role,
            "phoneNumber": self.phone_number,
            "guardianPhoneNumber": self.guardian_phone_number,
            "createdAt": self.created_at
        }

    @classmethod
    def register(
        cls,
        db,
        phone_number,
        role="buyer",
        password="",
        guardian_phone_number=""
    ):
        """Register a user. Returns True on success."""
        phone_number = normalize_phone(phone_number)
        role = str(role).strip().lower()

        if not phone_number:
            raise ValueError("phoneNumber is required.")

        if role not in {"buyer", "admin", "seller"}:
            raise ValueError("role must be buyer, seller, or admin.")

        if len(password) < 6:
            raise ValueError("Password must contain at least 6 characters.")

        existing = cls.find_by_phone(db, phone_number)
        if existing is not None:
            raise ValueError("Phone number is already registered.")

        user_id = secrets.token_hex(8)
        created_at = now_iso()
        password_hash = hash_password(password)

        connection = db.connect()
        try:
            connection.execute(
                """
                INSERT INTO users (
                    id,
                    verified,
                    role,
                    phone_number,
                    password_hash,
                    guardian_phone_number,
                    created_at
                )
                VALUES (?, 0, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    role,
                    phone_number,
                    password_hash,
                    guardian_phone_number,
                    created_at
                )
            )

            if role == "buyer":
                connection.execute(
                    """
                    INSERT INTO buyer_profiles (
                        user_id,
                        working_hours,
                        latitude,
                        longitude
                    )
                    VALUES (?, '08:00-18:00', 0.0, 0.0)
                    """,
                    (user_id,)
                )

            connection.commit()
        finally:
            connection.close()

        return True

    @classmethod
    def login(cls, db, phone_number, password):
        """
        UML login method.
        Returns the userId string when credentials are valid.
        """
        user = cls.find_by_phone(db, phone_number)

        if user is None:
            return ""

        if not verify_password(password, user.password_hash):
            return ""

        return user.user_id

    @classmethod
    def find_by_phone(cls, db, phone_number):
        connection = db.connect()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM users
                WHERE phone_number = ?
                """,
                (normalize_phone(phone_number),)
            ).fetchone()
        finally:
            connection.close()

        return cls.from_row(row) if row else None

    @classmethod
    def find_by_id(cls, db, user_id):
        connection = db.connect()
        try:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,)
            ).fetchone()
        finally:
            connection.close()

        return cls.from_row(row) if row else None

    @classmethod
    def from_row(cls, row):
        return cls(
            row["id"],
            row["verified"],
            row["role"],
            row["phone_number"],
            row["password_hash"],
            row["guardian_phone_number"],
            row["created_at"]
        )

    def notify_buyer(
        self,
        db,
        buyer_id,
        material_category_id,
        seller_latitude=0.0,
        seller_longitude=0.0
    ):
        """Create a notification for the buyer."""
        category = MaterialCategory.find_by_id(
            db,
            material_category_id
        )

        if category is None:
            raise ValueError("Material category does not exist.")

        buyer = User.find_by_id(db, buyer_id)

        if buyer is None:
            raise ValueError("Buyer does not exist.")

        if self.role not in {"seller", "admin"}:
            raise ValueError(
                "Only a seller or admin can notify a buyer."
            )

        profile = BuyerProfile.find_by_user_id(db, buyer_id)

        estimated_distance = 0.0
        if profile is not None:
            estimated_distance = distance_km(
                seller_latitude,
                seller_longitude,
                profile.latitude,
                profile.longitude
            )

        notification_id = secrets.token_hex(8)

        notification = Notification(
            notification_id,
            self.user_id,
            buyer_id,
            material_category_id,
            seller_latitude,
            seller_longitude,
            round(estimated_distance, 2),
            now_iso(),
            "unread",
            now_iso()
        )

        notification.save(db)
        return True


# ============================================================
# BUYER PROFILE
# UML:
# userId:string
# workingHours:string
# latitude:float
# longitude:float
# updateLocation(...)
# ============================================================

class BuyerProfile:

    def __init__(
        self,
        user_id,
        working_hours,
        latitude,
        longitude
    ):
        self.user_id = user_id
        self.working_hours = working_hours
        self.latitude = float(latitude)
        self.longitude = float(longitude)

    @classmethod
    def find_by_user_id(cls, db, user_id):
        connection = db.connect()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM buyer_profiles
                WHERE user_id = ?
                """,
                (user_id,)
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return cls(
            row["user_id"],
            row["working_hours"],
            row["latitude"],
            row["longitude"]
        )

    def update_location(self, db, latitude, longitude):
        """UML: updateLocation(latitude, longitude): boolean."""
        latitude = safe_float(latitude, "latitude")
        longitude = safe_float(longitude, "longitude")

        if not -90 <= latitude <= 90:
            raise ValueError("latitude must be between -90 and 90.")

        if not -180 <= longitude <= 180:
            raise ValueError("longitude must be between -180 and 180.")

        connection = db.connect()
        try:
            cursor = connection.execute(
                """
                UPDATE buyer_profiles
                SET latitude = ?, longitude = ?
                WHERE user_id = ?
                """,
                (latitude, longitude, self.user_id)
            )
            connection.commit()
        finally:
            connection.close()

        if cursor.rowcount == 0:
            raise ValueError("Buyer profile does not exist.")

        self.latitude = latitude
        self.longitude = longitude
        return True

    def to_dict(self):
        return {
            "userId": self.user_id,
            "workingHours": self.working_hours,
            "latitude": self.latitude,
            "longitude": self.longitude
        }


# ============================================================
# MATERIAL CATEGORY
# UML:
# name:string
# description:string
# referencePhotoUrl:string
# ============================================================

class MaterialCategory:

    def __init__(
        self,
        category_id,
        name,
        description,
        reference_photo_url
    ):
        self.category_id = category_id
        self.name = name
        self.description = description
        self.reference_photo_url = reference_photo_url

    @classmethod
    def find_by_id(cls, db, category_id):
        connection = db.connect()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM material_categories
                WHERE id = ?
                """,
                (category_id,)
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return cls(
            row["id"],
            row["name"],
            row["description"],
            row["reference_photo_url"]
        )

    @classmethod
    def all(cls, db):
        connection = db.connect()
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM material_categories
                ORDER BY name
                """
            ).fetchall()
        finally:
            connection.close()

        return [
            cls(
                row["id"],
                row["name"],
                row["description"],
                row["reference_photo_url"]
            ).to_dict()
            for row in rows
        ]

    def to_dict(self):
        return {
            "id": self.category_id,
            "name": self.name,
            "description": self.description,
            "referencePhotoUrl": self.reference_photo_url
        }


# ============================================================
# BUYER PRICES
# UML:
# materialCategoryId:string
# buyerId:string
# pricePerKilo:float
# updatedAt:string
# setPrice(...)
# ============================================================

class BuyerPrices:

    def __init__(
        self,
        material_category_id,
        buyer_id,
        price_per_kilo,
        updated_at
    ):
        self.material_category_id = material_category_id
        self.buyer_id = buyer_id
        self.price_per_kilo = float(price_per_kilo)
        self.updated_at = updated_at

    def set_price(self, db, material_category_id, new_price):
        """UML: setPrice(materialCategoryId, newPrice): boolean."""
        new_price = safe_float(new_price, "newPrice")

        if new_price <= 0:
            raise ValueError("newPrice must be greater than 0.")

        if MaterialCategory.find_by_id(
            db,
            material_category_id
        ) is None:
            raise ValueError("Material category does not exist.")

        if User.find_by_id(db, self.buyer_id) is None:
            raise ValueError("Buyer does not exist.")

        updated_at = now_iso()

        connection = db.connect()
        try:
            connection.execute(
                """
                INSERT INTO buyer_prices (
                    material_category_id,
                    buyer_id,
                    price_per_kilo,
                    updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(material_category_id, buyer_id)
                DO UPDATE SET
                    price_per_kilo = excluded.price_per_kilo,
                    updated_at = excluded.updated_at
                """,
                (
                    material_category_id,
                    self.buyer_id,
                    new_price,
                    updated_at
                )
            )
            connection.commit()
        finally:
            connection.close()

        self.material_category_id = material_category_id
        self.price_per_kilo = new_price
        self.updated_at = updated_at

        return True

    @classmethod
    def find(cls, db, buyer_id, material_category_id):
        connection = db.connect()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM buyer_prices
                WHERE buyer_id = ?
                  AND material_category_id = ?
                """,
                (buyer_id, material_category_id)
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return cls(
            row["material_category_id"],
            row["buyer_id"],
            row["price_per_kilo"],
            row["updated_at"]
        )

    @classmethod
    def for_buyer(cls, db, buyer_id):
        connection = db.connect()
        try:
            rows = connection.execute(
                """
                SELECT
                    bp.material_category_id,
                    bp.buyer_id,
                    bp.price_per_kilo,
                    bp.updated_at,
                    mc.name AS material_name
                FROM buyer_prices bp
                INNER JOIN material_categories mc
                    ON bp.material_category_id = mc.id
                WHERE bp.buyer_id = ?
                ORDER BY mc.name
                """,
                (buyer_id,)
            ).fetchall()
        finally:
            connection.close()

        return [
            {
                "materialCategoryId": row["material_category_id"],
                "materialName": row["material_name"],
                "buyerId": row["buyer_id"],
                "pricePerKilo": row["price_per_kilo"],
                "updatedAt": row["updated_at"]
            }
            for row in rows
        ]

    def to_dict(self):
        return {
            "materialCategoryId": self.material_category_id,
            "buyerId": self.buyer_id,
            "pricePerKilo": self.price_per_kilo,
            "updatedAt": self.updated_at
        }


# ============================================================
# TRANSACTION
# UML:
# buyerId:string
# sellerPhoneNumber:string
# sellerName:string
# materialCategoryId:string
# weightKg:float
# pricePerKilo:float
# photoUrl:string
# latitude:float
# longitude:float
# confirmedBySeller:boolean
# timestamp:string
# logTransaction(...): boolean
# ============================================================

class Transaction:

    def __init__(
        self,
        transaction_id,
        buyer_id,
        seller_phone_number,
        seller_name,
        material_category_id,
        weight_kg,
        price_per_kilo,
        photo_url,
        latitude,
        longitude,
        confirmed_by_seller,
        timestamp
    ):
        self.transaction_id = transaction_id
        self.buyer_id = buyer_id
        self.seller_phone_number = seller_phone_number
        self.seller_name = seller_name
        self.material_category_id = material_category_id
        self.weight_kg = float(weight_kg)
        self.price_per_kilo = float(price_per_kilo)
        self.photo_url = photo_url
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.confirmed_by_seller = bool(confirmed_by_seller)
        self.timestamp = timestamp

    def log_transaction(
        self,
        db,
        buyer_id,
        seller_phone_number,
        material_category_id,
        weight_kg,
        price_per_kilo,
        photo_url="",
        latitude=0.0,
        longitude=0.0
    ):
        """UML logTransaction(...): boolean."""
        if User.find_by_id(db, buyer_id) is None:
            raise ValueError("Buyer does not exist.")

        if MaterialCategory.find_by_id(
            db,
            material_category_id
        ) is None:
            raise ValueError("Material category does not exist.")

        weight_kg = safe_float(weight_kg, "weightKg")
        price_per_kilo = safe_float(price_per_kilo, "pricePerKilo")
        latitude = safe_float(latitude, "latitude")
        longitude = safe_float(longitude, "longitude")

        if weight_kg <= 0:
            raise ValueError("weightKg must be greater than 0.")

        if price_per_kilo <= 0:
            raise ValueError("pricePerKilo must be greater than 0.")

        if not -90 <= latitude <= 90:
            raise ValueError("latitude must be between -90 and 90.")

        if not -180 <= longitude <= 180:
            raise ValueError("longitude must be between -180 and 180.")

        transaction_id = secrets.token_hex(8)
        timestamp = now_iso()
        seller_phone_number = normalize_phone(seller_phone_number)

        connection = db.connect()
        try:
            connection.execute(
                """
                INSERT INTO transactions (
                    id,
                    buyer_id,
                    seller_phone_number,
                    seller_name,
                    material_category_id,
                    weight_kg,
                    price_per_kilo,
                    photo_url,
                    latitude,
                    longitude,
                    confirmed_by_seller,
                    timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    transaction_id,
                    buyer_id,
                    seller_phone_number,
                    self.seller_name,
                    material_category_id,
                    weight_kg,
                    price_per_kilo,
                    photo_url,
                    latitude,
                    longitude,
                    timestamp
                )
            )
            connection.commit()
        finally:
            connection.close()

        self.transaction_id = transaction_id
        self.buyer_id = buyer_id
        self.seller_phone_number = seller_phone_number
        self.material_category_id = material_category_id
        self.weight_kg = weight_kg
        self.price_per_kilo = price_per_kilo
        self.photo_url = photo_url
        self.latitude = latitude
        self.longitude = longitude
        self.confirmed_by_seller = False
        self.timestamp = timestamp

        return True

    @classmethod
    def history(cls, db, buyer_id):
        connection = db.connect()
        try:
            rows = connection.execute(
                """
                SELECT
                    t.*,
                    mc.name AS material_name
                FROM transactions t
                INNER JOIN material_categories mc
                    ON t.material_category_id = mc.id
                WHERE t.buyer_id = ?
                ORDER BY t.timestamp DESC
                """,
                (buyer_id,)
            ).fetchall()
        finally:
            connection.close()

        return [
            {
                "id": row["id"],
                "buyerId": row["buyer_id"],
                "sellerPhoneNumber": row["seller_phone_number"],
                "sellerName": row["seller_name"],
                "materialCategoryId": row["material_category_id"],
                "materialName": row["material_name"],
                "weightKg": row["weight_kg"],
                "pricePerKilo": row["price_per_kilo"],
                "totalAmount": round(
                    row["weight_kg"] * row["price_per_kilo"],
                    2
                ),
                "photoUrl": row["photo_url"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "confirmedBySeller": bool(
                    row["confirmed_by_seller"]
                ),
                "timestamp": row["timestamp"]
            }
            for row in rows
        ]


# ============================================================
# NOTIFICATION
# UML:
# sellerId:string
# buyerId:string
# materialCategoryId:string
# sellerLatitude:float
# sellerLongitude:float
# estimatedDistanceKm:float
# estimatedTime:Date and time
# status:string
# createdAt:string
# updateStatus(newStatus:boolean): boolean
# updateLocation(...): boolean
# ============================================================

class Notification:

    def __init__(
        self,
        notification_id,
        seller_id,
        buyer_id,
        material_category_id,
        seller_latitude,
        seller_longitude,
        estimated_distance_km,
        estimated_time,
        status,
        created_at
    ):
        self.notification_id = notification_id
        self.seller_id = seller_id
        self.buyer_id = buyer_id
        self.material_category_id = material_category_id
        self.seller_latitude = float(seller_latitude)
        self.seller_longitude = float(seller_longitude)
        self.estimated_distance_km = float(estimated_distance_km)
        self.estimated_time = estimated_time
        self.status = status
        self.created_at = created_at

    def save(self, db):
        connection = db.connect()
        try:
            connection.execute(
                """
                INSERT INTO notifications (
                    id,
                    seller_id,
                    buyer_id,
                    material_category_id,
                    seller_latitude,
                    seller_longitude,
                    estimated_distance_km,
                    estimated_time,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.notification_id,
                    self.seller_id,
                    self.buyer_id,
                    self.material_category_id,
                    self.seller_latitude,
                    self.seller_longitude,
                    self.estimated_distance_km,
                    self.estimated_time,
                    self.status,
                    self.created_at
                )
            )
            connection.commit()
        finally:
            connection.close()

        return True

    def update_status(self, db, new_status):
        """UML says boolean; accepts bool or status string."""
        if isinstance(new_status, bool):
            status = "read" if new_status else "unread"
        else:
            status = str(new_status).strip().lower()

        allowed = {
            "unread",
            "read",
            "accepted",
            "rejected",
            "completed"
        }

        if status not in allowed:
            raise ValueError(
                "Invalid status. Use unread, read, accepted, "
                "rejected, or completed."
            )

        connection = db.connect()
        try:
            cursor = connection.execute(
                """
                UPDATE notifications
                SET status = ?
                WHERE id = ?
                """,
                (status, self.notification_id)
            )
            connection.commit()
        finally:
            connection.close()

        if cursor.rowcount == 0:
            raise ValueError("Notification does not exist.")

        self.status = status
        return True

    def update_location(self, db, new_latitude, new_longitude):
        """UML: updateLocation(newLatitude, newLongitude): boolean."""
        new_latitude = safe_float(new_latitude, "newLatitude")
        new_longitude = safe_float(new_longitude, "newLongitude")

        if not -90 <= new_latitude <= 90:
            raise ValueError("newLatitude must be between -90 and 90.")

        if not -180 <= new_longitude <= 180:
            raise ValueError(
                "newLongitude must be between -180 and 180."
            )

        buyer = BuyerProfile.find_by_user_id(
            db,
            self.buyer_id
        )

        if buyer is None:
            raise ValueError("Buyer profile does not exist.")

        self.seller_latitude = new_latitude
        self.seller_longitude = new_longitude

        self.estimated_distance_km = round(
            distance_km(
                new_latitude,
                new_longitude,
                buyer.latitude,
                buyer.longitude
            ),
            2
        )

        self.estimated_time = now_iso()

        connection = db.connect()
        try:
            connection.execute(
                """
                UPDATE notifications
                SET
                    seller_latitude = ?,
                    seller_longitude = ?,
                    estimated_distance_km = ?,
                    estimated_time = ?
                WHERE id = ?
                """,
                (
                    self.seller_latitude,
                    self.seller_longitude,
                    self.estimated_distance_km,
                    self.estimated_time,
                    self.notification_id
                )
            )
            connection.commit()
        finally:
            connection.close()

        return True

    @classmethod
    def find_by_id(cls, db, notification_id):
        connection = db.connect()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM notifications
                WHERE id = ?
                """,
                (notification_id,)
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return cls(
            row["id"],
            row["seller_id"],
            row["buyer_id"],
            row["material_category_id"],
            row["seller_latitude"],
            row["seller_longitude"],
            row["estimated_distance_km"],
            row["estimated_time"],
            row["status"],
            row["created_at"]
        )

    @classmethod
    def for_buyer(cls, db, buyer_id):
        connection = db.connect()
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM notifications
                WHERE buyer_id = ?
                ORDER BY created_at DESC
                """,
                (buyer_id,)
            ).fetchall()
        finally:
            connection.close()

        return [
            cls(
                row["id"],
                row["seller_id"],
                row["buyer_id"],
                row["material_category_id"],
                row["seller_latitude"],
                row["seller_longitude"],
                row["estimated_distance_km"],
                row["estimated_time"],
                row["status"],
                row["created_at"]
            ).to_dict()
            for row in rows
        ]

    def to_dict(self):
        return {
            "id": self.notification_id,
            "sellerId": self.seller_id,
            "buyerId": self.buyer_id,
            "materialCategoryId": self.material_category_id,
            "sellerLatitude": self.seller_latitude,
            "sellerLongitude": self.seller_longitude,
            "estimatedDistanceKm": self.estimated_distance_km,
            "estimatedTime": self.estimated_time,
            "status": self.status,
            "createdAt": self.created_at
        }


# ============================================================
# CHAT MESSAGE
# UML:
# notificationId:string
# senderId:string
# messageText:string
# timestamp:string
# sendMessage(...): boolean
# ============================================================

class ChatMessage:

    def __init__(
        self,
        message_id,
        notification_id,
        sender_id,
        message_text,
        timestamp
    ):
        self.message_id = message_id
        self.notification_id = notification_id
        self.sender_id = sender_id
        self.message_text = message_text
        self.timestamp = timestamp

    @classmethod
    def send_message(
        cls,
        db,
        notification_id,
        sender_id,
        message_text
    ):
        """UML: sendMessage(...): boolean."""
        notification = Notification.find_by_id(
            db,
            notification_id
        )

        if notification is None:
            raise ValueError("Notification does not exist.")

        if User.find_by_id(db, sender_id) is None:
            raise ValueError("Sender does not exist.")

        message_text = str(message_text).strip()

        if not message_text:
            raise ValueError("messageText cannot be empty.")

        timestamp = now_iso()

        connection = db.connect()
        try:
            cursor = connection.execute(
                """
                INSERT INTO chat_messages (
                    notification_id,
                    sender_id,
                    message_text,
                    timestamp
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    notification_id,
                    sender_id,
                    message_text,
                    timestamp
                )
            )
            connection.commit()
            message_id = cursor.lastrowid
        finally:
            connection.close()

        return message_id

    @classmethod
    def for_notification(cls, db, notification_id):
        connection = db.connect()
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM chat_messages
                WHERE notification_id = ?
                ORDER BY timestamp ASC
                """,
                (notification_id,)
            ).fetchall()
        finally:
            connection.close()

        return [
            {
                "id": row["id"],
                "notificationId": row["notification_id"],
                "senderId": row["sender_id"],
                "messageText": row["message_text"],
                "timestamp": row["timestamp"]
            }
            for row in rows
        ]


# ============================================================
# HTTP API
# Standard library only: no Flask installation required.
# ============================================================

class MarketplaceAPI(BaseHTTPRequestHandler):
    """HTTP controller for the UML domain classes."""

    database = Database()

    def log_message(self, format_string, *args):
        print(
            f"{self.address_string()} - "
            f"{format_string % args}"
        )

    def send_json(self, status, payload, set_cookie=None):
        body = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        ).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )
        self.send_header("Content-Length", str(len(body)))

        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)

        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        content_length = int(
            self.headers.get("Content-Length", "0")
        )

        raw_body = self.rfile.read(content_length)

        if not raw_body:
            return {}

        try:
            data = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            raise ValueError("Request body contains invalid JSON.")

        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object.")

        return data

    def path_parts(self):
        parsed = urlparse(self.path)
        parts = [
            part for part in parsed.path.split("/")
            if part
        ]
        return parsed, parts

    def get_session_user_id(self):
        """Read the logged-in user from an HTTP-only cookie."""
        cookie_header = self.headers.get("Cookie", "")

        if not cookie_header:
            return None

        cookies = SimpleCookie()
        cookies.load(cookie_header)

        session_cookie = cookies.get("session_user")

        if session_cookie is None:
            return None

        value = session_cookie.value

        try:
            user_id, signature = value.split(".", 1)
        except ValueError:
            return None

        expected = hmac.new(
            Config.SESSION_SECRET.encode("utf-8"),
            user_id.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if hmac.compare_digest(signature, expected):
            return user_id

        return None

    @staticmethod
    def make_session_cookie(user_id):
        signature = hmac.new(
            Config.SESSION_SECRET.encode("utf-8"),
            user_id.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return (
            f"session_user={user_id}.{signature}; "
            "HttpOnly; Path=/; SameSite=Lax"
        )

    def require_user(self):
        user_id = self.get_session_user_id()

        if not user_id:
            self.send_json(
                HTTPStatus.UNAUTHORIZED,
                {"error": "You must log in first."}
            )
            return None

        user = User.find_by_id(
            self.database,
            user_id
        )

        if user is None:
            self.send_json(
                HTTPStatus.UNAUTHORIZED,
                {"error": "Session user does not exist."}
            )
            return None

        return user

    def require_buyer(self):
        user = self.require_user()

        if user is None:
            return None

        if user.role != "buyer":
            self.send_json(
                HTTPStatus.FORBIDDEN,
                {"error": "Buyer access required."}
            )
            return None

        return user

    def require_admin(self):
        user = self.require_user()

        if user is None:
            return None

        if user.role != "admin":
            self.send_json(
                HTTPStatus.FORBIDDEN,
                {"error": "Admin access required."}
            )
            return None

        return user

    def do_GET(self):
        parsed, parts = self.path_parts()

        try:
            if parsed.path == "/":
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "message": "Recycling Marketplace API",
                        "status": "running",
                        "uml": [
                            "User",
                            "BuyerProfile",
                            "BuyerPrices",
                            "MaterialCategory",
                            "Transaction",
                            "Notification",
                            "ChatMessage"
                        ]
                    }
                )
                return

            if parsed.path == "/api/material-categories":
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "materials": MaterialCategory.all(
                            self.database
                        )
                    }
                )
                return

            if parsed.path == "/api/me":
                user = self.require_user()
                if user is None:
                    return

                profile = None
                if user.role == "buyer":
                    profile = BuyerProfile.find_by_user_id(
                        self.database,
                        user.user_id
                    )

                self.send_json(
                    HTTPStatus.OK,
                    {
                        "user": user.to_dict(),
                        "profile": (
                            profile.to_dict()
                            if profile else None
                        )
                    }
                )
                return

            if parts[:3] == ["api", "buyer", "price-requests"]:
                user = self.require_buyer()
                if user is None:
                    return

                self.send_json(
                    HTTPStatus.OK,
                    {
                        "prices": BuyerPrices.for_buyer(
                            self.database,
                            user.user_id
                        )
                    }
                )
                return

            if parts[:3] == ["api", "buyer", "transactions"]:
                user = self.require_buyer()
                if user is None:
                    return

                self.send_json(
                    HTTPStatus.OK,
                    {
                        "transactions": Transaction.history(
                            self.database,
                            user.user_id
                        )
                    }
                )
                return

            if parts[:3] == ["api", "buyer", "notifications"]:
                user = self.require_buyer()
                if user is None:
                    return

                self.send_json(
                    HTTPStatus.OK,
                    {
                        "notifications": Notification.for_buyer(
                            self.database,
                            user.user_id
                        )
                    }
                )
                return

            if len(parts) == 4 and parts[:2] == ["api", "chat"]:
                # /api/chat/notification/<id>
                if parts[2] != "notification":
                    self.send_json(
                        HTTPStatus.NOT_FOUND,
                        {"error": "Route not found."}
                    )
                    return

            if (
                len(parts) == 4
                and parts[0:3] == ["api", "chat", "notification"]
            ):
                user = self.require_user()
                if user is None:
                    return

                notification_id = parts[3]
                notification = Notification.find_by_id(
                    self.database,
                    notification_id
                )

                if notification is None:
                    self.send_json(
                        HTTPStatus.NOT_FOUND,
                        {"error": "Notification not found."}
                    )
                    return

                if user.user_id not in {
                    notification.buyer_id,
                    notification.seller_id
                }:
                    self.send_json(
                        HTTPStatus.FORBIDDEN,
                        {"error": "You cannot view this conversation."}
                    )
                    return

                self.send_json(
                    HTTPStatus.OK,
                    {
                        "messages": ChatMessage.for_notification(
                            self.database,
                            notification_id
                        )
                    }
                )
                return

            if (
                len(parts) == 3
                and parts[:2] == ["api", "admin"]
                and parts[2] == "transactions"
            ):
                user = self.require_admin()
                if user is None:
                    return

                self.send_json(
                    HTTPStatus.OK,
                    {
                        "transactions": self._all_transactions()
                    }
                )
                return

            self.send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "Route not found."}
            )

        except Exception as exc:
            self.send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "Internal server error.",
                    "details": str(exc)
                }
            )

    def do_POST(self):
        parsed, parts = self.path_parts()

        try:
            # ------------------------------------------------
            # REGISTER
            # ------------------------------------------------
            if parsed.path == "/api/register":
                data = self.read_json()

                User.register(
                    self.database,
                    data.get("phoneNumber", ""),
                    data.get("role", "buyer"),
                    data.get("password", ""),
                    data.get("guardianPhoneNumber", "")
                )

                user = User.find_by_phone(
                    self.database,
                    data.get("phoneNumber", "")
                )

                self.send_json(
                    HTTPStatus.CREATED,
                    {
                        "message": "Registration successful.",
                        "user": user.to_dict()
                    }
                )
                return

            # ------------------------------------------------
            # LOGIN
            # ------------------------------------------------
            if parsed.path == "/api/login":
                data = self.read_json()

                user_id = User.login(
                    self.database,
                    data.get("phoneNumber", ""),
                    data.get("password", "")
                )

                if not user_id:
                    self.send_json(
                        HTTPStatus.UNAUTHORIZED,
                        {"error": "Invalid phone number or password."}
                    )
                    return

                user = User.find_by_id(
                    self.database,
                    user_id
                )

                self.send_json(
                    HTTPStatus.OK,
                    {
                        "message": "Login successful.",
                        "user": user.to_dict()
                    },
                    set_cookie=self.make_session_cookie(user_id)
                )
                return

            # ------------------------------------------------
            # LOGOUT
            # ------------------------------------------------
            if parsed.path == "/api/logout":
                self.send_json(
                    HTTPStatus.OK,
                    {"message": "Logout successful."},
                    set_cookie=(
                        "session_user=deleted; "
                        "HttpOnly; Path=/; Max-Age=0"
                    )
                )
                return

            # ------------------------------------------------
            # BUYER LOCATION
            # ------------------------------------------------
            if parsed.path == "/api/buyer/profile/location":
                user = self.require_buyer()
                if user is None:
                    return

                data = self.read_json()
                profile = BuyerProfile.find_by_user_id(
                    self.database,
                    user.user_id
                )

                if profile is None:
                    self.send_json(
                        HTTPStatus.NOT_FOUND,
                        {"error": "Buyer profile not found."}
                    )
                    return

                profile.update_location(
                    self.database,
                    data.get("latitude"),
                    data.get("longitude")
                )

                self.send_json(
                    HTTPStatus.OK,
                    {
                        "message": "Buyer location updated.",
                        "profile": profile.to_dict()
                    }
                )
                return

            # ------------------------------------------------
            # BUYER SET PRICE
            # ------------------------------------------------
            if parsed.path == "/api/buyer/set-price":
                user = self.require_buyer()
                if user is None:
                    return

                data = self.read_json()

                price_object = BuyerPrices(
                    data.get("materialCategoryId", ""),
                    user.user_id,
                    0.0,
                    now_iso()
                )

                price_object.set_price(
                    self.database,
                    data.get("materialCategoryId", ""),
                    data.get("newPrice")
                )

                self.send_json(
                    HTTPStatus.OK,
                    {
                        "message": "Buyer price updated successfully.",
                        "price": price_object.to_dict()
                    }
                )
                return

            # ------------------------------------------------
            # LOG TRANSACTION
            # ------------------------------------------------
            if parsed.path == "/api/buyer/transactions":
                user = self.require_buyer()
                if user is None:
                    return

                data = self.read_json()

                transaction = Transaction(
                    transaction_id="",
                    buyer_id=user.user_id,
                    seller_phone_number=data.get(
                        "sellerPhoneNumber", ""
                    ),
                    seller_name=str(
                        data.get("sellerName", "Unknown Seller")
                    ),
                    material_category_id=data.get(
                        "materialCategoryId", ""
                    ),
                    weight_kg=0,
                    price_per_kilo=0,
                    photo_url=str(
                        data.get("photoUrl", "")
                    ),
                    latitude=0,
                    longitude=0,
                    confirmed_by_seller=False,
                    timestamp=now_iso()
                )

                transaction.log_transaction(
                    self.database,
                    user.user_id,
                    data.get("sellerPhoneNumber", ""),
                    data.get("materialCategoryId", ""),
                    data.get("weightKg"),
                    data.get("pricePerKilo"),
                    data.get("photoUrl", ""),
                    data.get("latitude", 0.0),
                    data.get("longitude", 0.0)
                )

                self.send_json(
                    HTTPStatus.CREATED,
                    {
                        "message": "Transaction logged successfully.",
                        "transaction": {
                            "id": transaction.transaction_id,
                            "buyerId": transaction.buyer_id,
                            "sellerPhoneNumber": (
                                transaction.seller_phone_number
                            ),
                            "sellerName": transaction.seller_name,
                            "materialCategoryId": (
                                transaction.material_category_id
                            ),
                            "weightKg": transaction.weight_kg,
                            "pricePerKilo": (
                                transaction.price_per_kilo
                            ),
                            "totalAmount": round(
                                transaction.weight_kg
                                * transaction.price_per_kilo,
                                2
                            ),
                            "photoUrl": transaction.photo_url,
                            "latitude": transaction.latitude,
                            "longitude": transaction.longitude,
                            "confirmedBySeller": (
                                transaction.confirmed_by_seller
                            ),
                            "timestamp": transaction.timestamp
                        }
                    }
                )
                return

            # ------------------------------------------------
            # NOTIFY BUYER (seller/admin)
            # ------------------------------------------------
            if parsed.path == "/api/notifications":
                user = self.require_user()
                if user is None:
                    return

                if user.role not in {"seller", "admin"}:
                    self.send_json(
                        HTTPStatus.FORBIDDEN,
                        {"error": "Only seller or admin can notify a buyer."}
                    )
                    return

                data = self.read_json()

                user.notify_buyer(
                    self.database,
                    data.get("buyerId", ""),
                    data.get("materialCategoryId", ""),
                    data.get("sellerLatitude", 0.0),
                    data.get("sellerLongitude", 0.0)
                )

                self.send_json(
                    HTTPStatus.CREATED,
                    {"message": "Buyer notified successfully."}
                )
                return

            # ------------------------------------------------
            # UPDATE NOTIFICATION STATUS
            # ------------------------------------------------
            if (
                len(parts) == 3
                and parts[:2] == ["api", "notifications"]
            ):
                user = self.require_user()
                if user is None:
                    return

                notification = Notification.find_by_id(
                    self.database,
                    parts[2]
                )

                if notification is None:
                    self.send_json(
                        HTTPStatus.NOT_FOUND,
                        {"error": "Notification not found."}
                    )
                    return

                if user.user_id not in {
                    notification.buyer_id,
                    notification.seller_id
                }:
                    self.send_json(
                        HTTPStatus.FORBIDDEN,
                        {"error": "You cannot update this notification."}
                    )
                    return

                data = self.read_json()

                notification.update_status(
                    self.database,
                    data.get("newStatus")
                )

                self.send_json(
                    HTTPStatus.OK,
                    {
                        "message": "Notification status updated.",
                        "notification": notification.to_dict()
                    }
                )
                return

            # ------------------------------------------------
            # UPDATE NOTIFICATION LOCATION
            # ------------------------------------------------
            if (
                len(parts) == 3
                and parts[:2] == ["api", "notification-location"]
            ):
                user = self.require_user()
                if user is None:
                    return

                notification = Notification.find_by_id(
                    self.database,
                    parts[2]
                )

                if notification is None:
                    self.send_json(
                        HTTPStatus.NOT_FOUND,
                        {"error": "Notification not found."}
                    )
                    return

                if user.user_id not in {
                    notification.buyer_id,
                    notification.seller_id
                }:
                    self.send_json(
                        HTTPStatus.FORBIDDEN,
                        {"error": "You cannot update this notification."}
                    )
                    return

                data = self.read_json()

                notification.update_location(
                    self.database,
                    data.get("newLatitude"),
                    data.get("newLongitude")
                )

                self.send_json(
                    HTTPStatus.OK,
                    {
                        "message": "Notification location updated.",
                        "notification": notification.to_dict()
                    }
                )
                return

            # ------------------------------------------------
            # SEND CHAT MESSAGE
            # ------------------------------------------------
            if parsed.path == "/api/chat/send":
                user = self.require_user()
                if user is None:
                    return

                data = self.read_json()

                notification = Notification.find_by_id(
                    self.database,
                    data.get("notificationId", "")
                )

                if notification is None:
                    self.send_json(
                        HTTPStatus.NOT_FOUND,
                        {"error": "Notification not found."}
                    )
                    return

                if user.user_id not in {
                    notification.buyer_id,
                    notification.seller_id
                }:
                    self.send_json(
                        HTTPStatus.FORBIDDEN,
                        {"error": "You cannot send this message."}
                    )
                    return

                message_id = ChatMessage.send_message(
                    self.database,
                    notification.notification_id,
                    user.user_id,
                    data.get("messageText", "")
                )

                self.send_json(
                    HTTPStatus.CREATED,
                    {
                        "message": "Chat message sent.",
                        "messageId": message_id
                    }
                )
                return

            self.send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "Route not found."}
            )

        except ValueError as exc:
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": str(exc)}
            )
        except sqlite3.IntegrityError as exc:
            self.send_json(
                HTTPStatus.CONFLICT,
                {
                    "error": "Database constraint error.",
                    "details": str(exc)
                }
            )
        except Exception as exc:
            self.send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "Internal server error.",
                    "details": str(exc)
                }
            )

    def _all_transactions(self):
        connection = self.database.connect()
        try:
            rows = connection.execute(
                """
                SELECT
                    t.*,
                    mc.name AS material_name
                FROM transactions t
                INNER JOIN material_categories mc
                    ON t.material_category_id = mc.id
                ORDER BY t.timestamp DESC
                """
            ).fetchall()
        finally:
            connection.close()

        return [
            {
                "id": row["id"],
                "buyerId": row["buyer_id"],
                "sellerPhoneNumber": row["seller_phone_number"],
                "sellerName": row["seller_name"],
                "materialCategoryId": row["material_category_id"],
                "materialName": row["material_name"],
                "weightKg": row["weight_kg"],
                "pricePerKilo": row["price_per_kilo"],
                "totalAmount": round(
                    row["weight_kg"] * row["price_per_kilo"],
                    2
                ),
                "confirmedBySeller": bool(
                    row["confirmed_by_seller"]
                ),
                "timestamp": row["timestamp"]
            }
            for row in rows
        ]


# ============================================================
# SERVER
# ============================================================

def create_server():
    return ThreadingHTTPServer(
        (Config.HOST, Config.PORT),
        MarketplaceAPI
    )


def main():
    server = create_server()

    print("=" * 65)
    print("             RECYCLING MARKETPLACE API")
    print("=" * 65)
    print(f"Server   : http://{Config.HOST}:{Config.PORT}")
    print(f"Database : {Config.DATABASE}")
    print("Framework: Python standard library (no Flask required)")
    print("Press CTRL+C to stop.")
    print("=" * 65)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
