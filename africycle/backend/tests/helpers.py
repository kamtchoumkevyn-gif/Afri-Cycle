import jwt
from datetime import datetime, timedelta
import phones
from config import Config
from database.db import get_connection
from models.user import create_user
from models.material_category import create_material_category
from models.buyer_profile import create_buyer_profile
from models.buyer_price import set_price
from models.notification import create_notification


def make_token(user_id, role, two_step=True):
    """A login token. An admin's account counts as approved by another admin, and the
    token as logged in with the two-step code (their account gets two-step login turned
    on), unless two_step=False."""
    payload = {
        "userId": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    if role == "admin":
        conn = get_connection()
        conn.cursor().execute("UPDATE users SET adminApproved = 1 WHERE id = ?", (user_id,))
        if two_step:
            payload["mfa"] = True
            conn.cursor().execute("UPDATE users SET totpEnabled = 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
    return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")


def auth_header(user_id, role):
    return {"Authorization": f"Bearer {make_token(user_id, role)}"}


def new_user(phone, role, name="Test User"):
    """Saved like a sign-up saves it: "677000001" becomes +237677000001."""
    return create_user(phones.stored_form(phone), "password123", name, role)


def new_category(name="Scrap Iron"):
    return create_material_category(name, "http://example.com/photo.jpg")


def new_buyer_with_profile(phone, lat, lng, price, category_id, name="Test Buyer"):
    buyer_id = new_user(phone, "buyer", name)
    create_buyer_profile(buyer_id, lat, lng, "8am-6pm")
    set_price(buyer_id, category_id, price)
    return buyer_id


def came_by(seller_id, buyer_id, category_id=None):
    """The seller told the buyer they're bringing material (a trip). The two now deal
    with each other: they can exchange messages, and the buyer can record a purchase."""
    if category_id is None:
        category_id = new_category(f"Material {seller_id}-{buyer_id}")
    return create_notification(seller_id, buyer_id, category_id)
