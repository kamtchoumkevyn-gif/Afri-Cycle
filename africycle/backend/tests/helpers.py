import jwt
from datetime import datetime, timedelta
from config import Config
from models.user import create_user
from models.material_category import create_material_category
from models.buyer_profile import create_buyer_profile
from models.buyer_price import set_price


def make_token(user_id, role):
    payload = {
        "userId": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")


def auth_header(user_id, role):
    return {"Authorization": f"Bearer {make_token(user_id, role)}"}


def new_user(phone, role, name="Test User"):
    return create_user(phone, "password123", name, role)


def new_category(name="Scrap Iron"):
    return create_material_category(name, "http://example.com/photo.jpg")


def new_buyer_with_profile(phone, lat, lng, price, category_id, name="Test Buyer"):
    buyer_id = new_user(phone, "buyer", name)
    create_buyer_profile(buyer_id, lat, lng, "8am-6pm")
    set_price(buyer_id, category_id, price)
    return buyer_id
