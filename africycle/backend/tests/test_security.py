import base64
import hashlib
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta

import jwt

from app import CONTENT_SECURITY_POLICY, FRONTEND_DIR
from config import Config
from helpers import auth_header, new_user, new_category
from models.notification import create_notification, get_notification_by_id

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def post_raw_json(client, url, raw_body, headers):
    """Sends the body exactly as written, so tests can use NaN / Infinity like an attacker could."""
    return client.post(url, data=raw_body, content_type="application/json", headers=headers)


# ---- Startup ----

def test_app_refuses_to_start_without_secret_key(tmp_path):
    # Copy config.py somewhere with no .env file next to it, then import it without the variable
    shutil.copy(os.path.join(BACKEND_DIR, "config.py"), tmp_path)
    env = {k: v for k, v in os.environ.items() if k != "JWT_SECRET_KEY"}
    result = subprocess.run([sys.executable, "-c", "import config"], cwd=tmp_path,
                            env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "JWT_SECRET_KEY" in result.stderr


# ---- Security headers ----

def test_security_headers_on_pages_and_api(client):
    for path in ("/", "/login.html", "/health"):
        headers = client.get(path).headers
        assert headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert "max-age=" in headers["Strict-Transport-Security"]


def test_pages_load_nothing_from_other_sites():
    # Fonts, styles, scripts and the map library are all served by this app, so a slow
    # or blocked outside server can't hold a page up. (Only map tiles come from
    # OpenStreetMap, and only as images.)
    for name in os.listdir(FRONTEND_DIR):
        if not name.endswith(".html"):
            continue
        with open(os.path.join(FRONTEND_DIR, name), encoding="utf-8") as f:
            html = f.read()
        assert not re.search(r'<(?:link|script)[^>]+(?:href|src)="(?:https?:)?//', html), name
    assert "googleapis" not in CONTENT_SECURITY_POLICY
    assert "style-src 'self';" in CONTENT_SECURITY_POLICY


def test_csp_allows_every_inline_script_in_the_frontend():
    # If this fails, an inline <script> was added or edited: put its hash in app.py,
    # or better, move the script into a file under frontend/js/.
    for name in os.listdir(FRONTEND_DIR):
        if not name.endswith(".html"):
            continue
        with open(os.path.join(FRONTEND_DIR, name), encoding="utf-8") as f:
            html = f.read()
        for script in re.findall(r"<script>(.*?)</script>", html, re.S):
            digest = hashlib.sha256(script.replace("\r\n", "\n").encode("utf-8")).digest()
            expected = "'sha256-" + base64.b64encode(digest).decode() + "'"
            assert expected in CONTENT_SECURITY_POLICY, f"{name}: add {expected} to script-src in app.py"


# ---- Frontend files ----

def test_every_frontend_file_is_served(client):
    for folder, _, files in os.walk(FRONTEND_DIR):
        for name in files:
            path = os.path.relpath(os.path.join(folder, name), FRONTEND_DIR).replace(os.sep, "/")
            assert client.get("/" + path).status_code == 200, path


def test_paths_outside_frontend_are_refused(client):
    for path in ("/../backend/config.py", "/%2e%2e/backend/config.py", "/..%2fbackend%2fconfig.py",
                 "/js/../../backend/app.py", "/js/%2e%2e/%2e%2e/backend/app.py", "/../.env"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert b"SECRET_KEY" not in response.data


# ---- Tokens ----

def test_expired_token_is_rejected(client):
    user = new_user("677000001", "buyer")
    token = jwt.encode({"userId": user, "role": "buyer", "exp": datetime.utcnow() - timedelta(minutes=1)},
                       Config.SECRET_KEY, algorithm="HS256")
    response = client.get("/buyer/prices", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_token_signed_with_another_key_is_rejected(client):
    user = new_user("677000001", "buyer")
    token = jwt.encode({"userId": user, "role": "buyer", "exp": datetime.utcnow() + timedelta(hours=1)},
                       "not-the-real-key", algorithm="HS256")
    response = client.get("/buyer/prices", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# ---- Number checks ----

def test_set_price_rejects_bad_numbers(client):
    buyer = new_user("677000002", "buyer")
    category = new_category()
    headers = auth_header(buyer, "buyer")
    for bad in ("-5", '"abc"', "NaN", "Infinity", "2000000", "true"):
        body = f'{{"materialCategoryId": {category}, "pricePerKg": {bad}}}'
        assert post_raw_json(client, "/buyer/set-price", body, headers).status_code == 400, bad
    body = f'{{"materialCategoryId": {category}, "pricePerKg": 150}}'
    assert post_raw_json(client, "/buyer/set-price", body, headers).status_code == 200


def test_buyer_profile_rejects_bad_coordinates(client):
    buyer = new_user("677000002", "buyer")
    headers = auth_header(buyer, "buyer")
    for lat, lng in (("100", "9.7"), ("4.05", "200"), ('"abc"', "9.7"), ("NaN", "9.7"), ("4.05", "-Infinity")):
        body = f'{{"latitude": {lat}, "longitude": {lng}}}'
        assert post_raw_json(client, "/buyer/profile", body, headers).status_code == 400, (lat, lng)
    assert client.post("/buyer/profile", json={"latitude": 4.05, "longitude": 9.7},
                       headers=headers).status_code == 200


def test_log_transaction_rejects_bad_numbers(client):
    seller = new_user("677000001", "seller")
    buyer = new_user("677000002", "buyer")
    category = new_category()
    headers = auth_header(buyer, "buyer")
    for weight, price in (("-1", "100"), ("NaN", "100"), ("10", "-100"), ("10", "Infinity")):
        body = (f'{{"sellerId": {seller}, "materialCategoryId": {category}, '
                f'"weightKg": {weight}, "pricePerKg": {price}}}')
        assert post_raw_json(client, "/buyer/log-transaction", body, headers).status_code == 400, (weight, price)
    ok = client.post("/buyer/log-transaction", json={
        "sellerId": seller, "materialCategoryId": category, "weightKg": 12.5, "pricePerKg": 150
    }, headers=headers)
    assert ok.status_code == 201


def test_seller_location_cannot_carry_html(client):
    # The buyer dashboard writes these values into a link's HTML, so text must never be stored
    seller = new_user("677000001", "seller")
    buyer = new_user("677000002", "buyer")
    nid = create_notification(seller, buyer, new_category())
    headers = auth_header(seller, "seller")

    attack = {"latitude": '"><img src=x onerror=alert(1)>', "longitude": 9.71}
    assert client.patch(f"/notifications/{nid}/location", json=attack, headers=headers).status_code == 400
    assert client.patch(f"/notifications/{nid}/location", json={"latitude": 95, "longitude": 9.71},
                        headers=headers).status_code == 400
    assert get_notification_by_id(nid)["sellerLatitude"] is None

    assert client.patch(f"/notifications/{nid}/location", json={"latitude": "4.06", "longitude": 9.71},
                        headers=headers).status_code == 200
    assert get_notification_by_id(nid)["sellerLatitude"] == 4.06


# ---- Phone numbers ----

def register(client, phone, role="seller"):
    return client.post("/register", json={
        "name": "Paul", "phoneNumber": phone, "password": "password123", "role": role
    })


def login(client, phone):
    return client.post("/login", json={"phoneNumber": phone, "password": "password123"})


def test_register_rejects_invalid_phone_numbers(client):
    for bad in ("12345", "677000001000", "abcdefghi", "577000001", "600000099", "+234 803 123 4567"):
        assert register(client, bad).status_code == 400, bad


def test_login_accepts_any_format_used_at_signup(client):
    assert register(client, "+237 677 000 001").status_code == 201
    assert login(client, "677000001").status_code == 200
    assert login(client, "+237677000001").status_code == 200
    assert login(client, "237 677 000 001").status_code == 200


def test_accounts_saved_before_the_phone_rule_can_still_log_in(client):
    new_user("+237677000003", "seller")  # stored exactly as typed, like older accounts
    assert login(client, "+237677000003").status_code == 200


def test_admin_list_matches_numbers_written_with_country_code(client, monkeypatch):
    monkeypatch.setattr(Config, "ADMIN_PHONE_NUMBERS", ["+237 699 999 998"])
    assert register(client, "699999998", role="admin").status_code == 201
