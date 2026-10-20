"""Suspended accounts, admins' two-step login, and the admin action log."""
import totp
from helpers import auth_header, make_token, new_user

ADMIN_PHONE = "699999999"  # listed in ADMIN_PHONE_NUMBERS (conftest.py)


def register_admin(client, phone=ADMIN_PHONE, name="Ada Admin"):
    response = client.post("/register", json={"name": name, "phoneNumber": phone,
                                              "password": "secret123", "role": "admin"})
    assert response.status_code == 201, response.get_json()
    return response.get_json()["userId"]


def login(client, phone=ADMIN_PHONE, code=None):
    body = {"phoneNumber": phone, "password": "secret123"}
    if code is not None:
        body["code"] = code
    return client.post("/login", json=body)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def turn_on_two_step(client, token):
    secret = client.post("/admin/two-step/setup", headers=bearer(token)).get_json()["secret"]
    response = client.post("/admin/two-step/enable", headers=bearer(token),
                           json={"code": totp.code_at(secret, totp.current_step())})
    assert response.status_code == 200, response.get_json()
    return secret, response.get_json()["token"]


def actions(client, token):
    return [a["action"] for a in client.get("/admin/actions", headers=bearer(token)).get_json()["actions"]]


# ---- The codes themselves ----

def test_codes_match_the_published_standard():
    # RFC 6238's test secret "12345678901234567890" at 59 seconds: 94287082 (8 digits)
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp.code_at(secret, totp.current_step(59)) == "287082"


def test_a_code_works_once_and_only_around_its_time():
    secret = totp.new_secret()
    now = 1_800_000_000
    step = totp.current_step(now)
    assert totp.check(secret, totp.code_at(secret, step), now=now) == step
    assert totp.check(secret, totp.code_at(secret, step - 1), now=now) == step - 1  # phone clock a bit behind
    assert totp.check(secret, totp.code_at(secret, step - 3), now=now) is None      # too old
    assert totp.check(secret, totp.code_at(secret, step), last_step=step, now=now) is None  # used already
    assert totp.check(secret, "12345", now=now) is None and totp.check(secret, "abcdef", now=now) is None


def test_the_secret_is_stored_encrypted():
    sealed = totp.seal("JBSWY3DPEHPK3PXP")
    assert "JBSWY3DPEHPK3PXP" not in sealed
    assert totp.unseal(sealed) == "JBSWY3DPEHPK3PXP"
    assert totp.unseal("not a sealed secret") is None


# ---- Suspended (flagged) accounts ----

def test_a_flagged_account_is_logged_out_and_cannot_log_back_in(client):
    seller = new_user("677000001", "seller", "Jean")
    admin = new_user(ADMIN_PHONE, "admin", "Ada")
    seller_headers = auth_header(seller, "seller")
    assert client.get("/me", headers=seller_headers).status_code == 200

    response = client.post(f"/admin/flag-account/{seller}", headers=auth_header(admin, "admin"),
                           json={"reason": "Selling stolen cables"})
    assert response.status_code == 200

    assert client.get("/me", headers=seller_headers).status_code == 401  # the old login stops working
    response = client.post("/login", json={"phoneNumber": "677000001", "password": "password123"})
    assert response.status_code == 403 and response.get_json()["code"] == "suspended"

    client.post(f"/admin/unflag-account/{seller}", headers=auth_header(admin, "admin"))
    assert client.post("/login", json={"phoneNumber": "677000001", "password": "password123"}).status_code == 200


def test_admins_cannot_be_flagged(client):
    admin = new_user(ADMIN_PHONE, "admin", "Ada")
    other = new_user("699999998", "admin", "Bob")
    make_token(other, "admin")  # approved by another admin
    response = client.post(f"/admin/flag-account/{other}", headers=auth_header(admin, "admin"), json={})
    assert response.status_code == 400
    response = client.post(f"/admin/flag-account/{admin}", headers=auth_header(admin, "admin"), json={})
    assert response.status_code == 400


def test_the_role_comes_from_the_account_not_the_token(client):
    seller = new_user("677000001", "seller", "Jean")
    # A token claiming "admin" for a seller's account opens no admin tools
    forged = make_token(seller, "admin", two_step=False)
    assert client.get("/admin/users", headers=bearer(forged)).status_code == 401
    assert client.get("/admin/users", headers=bearer(make_token(999, "admin", two_step=False))).status_code == 401


# ---- Two-step login ----

def test_an_admin_must_turn_on_two_step_login_before_the_admin_tools_open(client):
    register_admin(client)
    response = login(client)
    assert response.status_code == 200
    token = response.get_json()["token"]

    response = client.get("/admin/stats", headers=bearer(token))
    assert response.status_code == 403 and response.get_json()["code"] == "two_step_setup"
    assert client.get("/admin/users", headers=bearer(token)).status_code == 403
    assert client.post("/admin/guide-recordings", headers=bearer(token), json={}).status_code == 403

    setup = client.post("/admin/two-step/setup", headers=bearer(token)).get_json()
    assert setup["link"].startswith("otpauth://totp/Africycle:") and setup["secret"] in setup["link"]
    response = client.post("/admin/two-step/enable", headers=bearer(token), json={"code": "000000"})
    assert response.status_code == 400

    _, full_token = turn_on_two_step(client, token)
    assert client.get("/admin/stats", headers=bearer(full_token)).status_code == 200
    # The old password-only login still doesn't open the tools
    assert client.get("/admin/stats", headers=bearer(token)).status_code == 403


def test_logging_in_then_needs_the_code_and_each_code_works_once(client):
    register_admin(client)
    secret, _ = turn_on_two_step(client, login(client).get_json()["token"])

    response = login(client)
    assert response.status_code == 401 and response.get_json()["code"] == "two_step_required"
    assert "token" not in response.get_json()

    response = login(client, code="000000")
    assert response.status_code == 401 and response.get_json()["code"] == "two_step_required"

    # The code used to turn it on was this step's; the next step's code logs in
    code = totp.code_at(secret, totp.current_step() + 1)
    response = login(client, code=code)
    assert response.status_code == 200
    token = response.get_json()["token"]
    assert client.get("/admin/stats", headers=bearer(token)).status_code == 200

    assert login(client, code=code).status_code == 401  # the same code again is refused
    logged = actions(client, token)
    assert logged == ["wrong_code", "login", "wrong_code", "two_step_on", "login"]  # newest first


def test_sellers_and_buyers_log_in_as_before(client):
    new_user("677000001", "seller", "Jean")
    response = client.post("/login", json={"phoneNumber": "677000001", "password": "password123", "code": "1"})
    assert response.status_code == 200


def test_another_admin_can_reset_a_lost_two_step_login(client):
    ada = register_admin(client)
    bob = new_user("699999998", "admin", "Bob")  # tests list one admin number; Bob is added directly
    turn_on_two_step(client, login(client).get_json()["token"])
    bob_headers = auth_header(bob, "admin")

    assert client.post(f"/admin/two-step/reset/{bob}", headers=bob_headers).status_code == 400  # not yourself
    response = client.post(f"/admin/two-step/reset/{ada}", headers=bob_headers)
    assert response.status_code == 200

    response = login(client)  # Ada logs in with her password, then sets it up again
    assert response.status_code == 200
    assert client.get("/admin/stats", headers=bearer(response.get_json()["token"])).status_code == 403


def test_admin_actions_are_logged_and_only_admins_see_them(client):
    admin = new_user(ADMIN_PHONE, "admin", "Ada")
    seller = new_user("677000001", "seller", "Jean")
    headers = auth_header(admin, "admin")
    client.post(f"/admin/flag-account/{seller}", headers=headers, json={"reason": "Fake prices"})
    client.post(f"/admin/unflag-account/{seller}", headers=headers)

    rows = client.get("/admin/actions", headers=headers).get_json()["actions"]
    assert [r["action"] for r in rows] == ["unflag", "flag"]
    assert rows[1]["targetName"] == "Jean" and rows[1]["adminName"] == "Ada" and rows[1]["details"] == "Fake prices"

    assert client.get("/admin/actions", headers=auth_header(seller, "seller")).status_code == 401
    assert client.get("/admin/actions").status_code == 401


def test_admins_see_receipts_only_after_the_second_step(client):
    from test_receipts import people, record_purchase
    buyer, seller, category = people()
    receipt = record_purchase(client, buyer, seller, category)
    admin = new_user(ADMIN_PHONE, "admin", "Ada")
    password_only = make_token(admin, "admin", two_step=False)
    assert client.get(f"/receipts/{receipt}", headers=bearer(password_only)).status_code == 404
    assert client.get(f"/receipts/{receipt}", headers=auth_header(admin, "admin")).status_code == 200
