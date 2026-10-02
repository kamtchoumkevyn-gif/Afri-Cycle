import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Works whether .env sits in backend/ or in the project root
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv(os.path.join(BASE_DIR, "..", ".env"))


class Config:
    SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-only-insecure-key-change-me")

    ADMIN_PHONE_NUMBERS = [
        number.strip()
        for number in os.environ.get("ADMIN_PHONE_NUMBERS", "").split(",")
        if number.strip()
    ]

    JWT_EXPIRY_HOURS = 24
