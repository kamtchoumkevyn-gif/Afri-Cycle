from math import radians, cos, sin, asin, sqrt
from datetime import datetime
from database.db import get_db  # ADJUST: import path to match your project's DB connection helper


# ---------- SELLER VIEWS NEARBY BUYERS SORTED BY PRICE ----------

def calculate_distance(lat1, lon1, lat2, lon2):
    """Distance in km between two GPS points (Haversine formula)."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return 6371 * c  # Earth radius in km


def get_nearby_buyers_sorted_by_price(seller_lat, seller_lon, material_category_id, max_distance_km=20):
    """
    Returns buyers near the seller who buy the given material,
    sorted by price per kilo (highest first).
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT bp.userId, bp.latitude, bp.longitude,
               price.pricePerKilo, u.PhoneNumber
        FROM BuyerProfile bp
        JOIN BuyerPrices price ON price.buyerId = bp.userId
        JOIN User u ON u.userId = bp.userId
        WHERE price.materialCategoryId = ?
    """, (material_category_id,))

    rows = cursor.fetchall()

    nearby_buyers = []
    for buyer_id, lat, lon, price_per_kilo, phone in rows:
        distance = calculate_distance(seller_lat, seller_lon, lat, lon)
        if distance <= max_distance_km:
            nearby_buyers.append({
                "buyerId": buyer_id,
                "latitude": lat,
                "longitude": lon,
                "pricePerKilo": price_per_kilo,
                "phoneNumber": phone,
                "distanceKm": round(distance, 2)
            })

    nearby_buyers.sort(key=lambda b: b["pricePerKilo"], reverse=True)
    return nearby_buyers


# ---------- SELLER VIEWS BUYER PROFILE ----------

def get_buyer_profile(buyer_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT bp.userId, bp.workingHours, bp.latitude, bp.longitude, u.PhoneNumber
        FROM BuyerProfile bp
        JOIN User u ON u.userId = bp.userId
        WHERE bp.userId = ?
    """, (buyer_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "buyerId": row[0],
        "workingHours": row[1],
        "latitude": row[2],
        "longitude": row[3],
        "phoneNumber": row[4]
    }


# ---------- SELLER NOTIFIES BUYER WITH MATERIAL ----------

def create_notification(seller_id, buyer_id, material_category_id,
                         seller_lat, seller_lon, estimated_distance_km, estimated_time):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO Notification
            (sellerId, buyerId, materialCategoryId, sellerLatitude, sellerLongitude,
             estimatedDistanceKm, estimatedTime, status, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        seller_id, buyer_id, material_category_id,
        seller_lat, seller_lon, estimated_distance_km, estimated_time,
        "pending", datetime.utcnow().isoformat()
    ))
    db.commit()
    return cursor.lastrowid


# ---------- SELLER CLICKS REFERENCE PHOTO -> NOTIFY BUYER (with live tracking) ----------

def notify_buyer_from_reference_photo(seller_id, buyer_id, buyer_name, reference_photo_url,
                                       seller_lat, seller_lon, live_tracking_enabled=True):
    """
    Triggered when the seller clicks on a buyer's reference photo.
    Creates a notification containing:
      1) the buyer's name
      2) the seller's current geolocation
      3) info about the reference photo clicked
      4) a flag enabling live tracking for this notification

    NOTE: requires 3 extra columns on the Notification table:
    buyerName, referencePhotoUrl, liveTrackingEnabled.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO Notification
            (sellerId, buyerId, buyerName, referencePhotoUrl,
             sellerLatitude, sellerLongitude, liveTrackingEnabled,
             status, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        seller_id, buyer_id, buyer_name, reference_photo_url,
        seller_lat, seller_lon, int(live_tracking_enabled),
        "pending", datetime.utcnow().isoformat()
    ))
    db.commit()
    return cursor.lastrowid


# ---------- LIVE TRACKING: UPDATE SELLER'S POSITION ON AN ACTIVE NOTIFICATION ----------

def update_seller_live_location(notification_id, new_lat, new_lon):
    """
    Called repeatedly (e.g. every few seconds) while the seller is en route,
    so the buyer can see the seller's position update in real time.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE Notification
        SET sellerLatitude = ?, sellerLongitude = ?
        WHERE id = ?
    """, (new_lat, new_lon, notification_id))
    db.commit()
    return cursor.rowcount > 0


# ---------- SELLER CONTACTS BUYER TO ARRANGE MEETING ----------

def update_notification_status(notification_id, new_status):
    """Used both to mark a notification as 'contacted' and to update it later (e.g. 'confirmed')."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE Notification SET status = ? WHERE id = ?
    """, (new_status, notification_id))
    db.commit()
    return cursor.rowcount > 0