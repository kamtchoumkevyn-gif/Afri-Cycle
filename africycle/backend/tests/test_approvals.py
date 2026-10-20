"""Phone numbers aren't confirmed by SMS, so a number alone doesn't prove who someone is.

- A guardian approves (or declines) a child only with the 6-digit code shown on the
  child's phone, so someone who registered the guardian's number first can't.
- A new admin account opens no admin tool until an existing admin approves it, so
  someone who registered a listed admin number first gets nothing.
"""
import totp
from config import Config
from helpers import auth_header, make_token, new_user
from models.user import create_user, get_user_by_id

ADMIN_PHONE = "699999999"     # listed in ADMIN_PHONE_NUMBERS (conftest.py)
SECOND_ADMIN = "699999998"    # added to the list in the tests that need it


# ---- Children and their guardian's approval code ----

def register_child(client, phone="677000010", guardian_phone="699000001"):
    response = client.post("/register", json={
        "name": "Junior", "phoneNumber": phone, "password": "password123", "role": "seller",
        "isMinor": True, "guardianName": "Mama Junior", "guardianPhone": guardian_phone,
        "guardianRelation": "mother"})
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def me(client, user_id, role="seller"):
    return client.get("/me", headers=auth_header(user_id, role)).get_json()


def approve(client, guardian, child, code=None, action="approve"):
    body = {} if code is None else {"code": code}
    return client.post(f"/guardian/children/{child}/{action}", json=body,
                       headers=auth_header(guardian, "guardian"))


def wrong(code):
    return f"{(int(code) + 1) % 1_000_000:06d}"


def test_the_child_gets_a_code_that_only_the_child_sees(client):
    registered = register_child(client)
    child = registered["userId"]
    code = registered["approvalCode"]
    assert len(code) == 6 and code.isdigit()
    assert me(client, child)["approvalCode"] == code and me(client, child)["approvalCodeBlocked"] is False

    guardian = new_user("699000001", "guardian", "Mama Junior")
    assert "approvalCode" not in me(client, guardian, "guardian")
    pending = client.get("/guardian/children", headers=auth_header(guardian, "guardian")).get_json()["pending"]
    assert [c["id"] for c in pending] == [child]
    assert all("approvalCode" not in c and code not in str(c) for c in pending)


def test_a_guardian_needs_the_code_from_the_childs_phone(client):
    registered = register_child(client)
    child, code = registered["userId"], registered["approvalCode"]
    guardian = new_user("699000001", "guardian", "Mama Junior")

    for attempt in (approve(client, guardian, child), approve(client, guardian, child, wrong(code))):
        assert attempt.status_code == 400 and attempt.get_json()["code"] == "approval_code"
        assert "Junior" in attempt.get_json()["message"]
    assert get_user_by_id(child)["guardianStatus"] == "pending"

    # Typed with a space, the way the page shows it
    assert approve(client, guardian, child, code[:3] + " " + code[3:]).status_code == 200
    assert client.get("/seller/nearby-buyers?lat=4.05&lng=9.7",
                      headers=auth_header(child, "seller")).status_code == 200
    account = me(client, child)
    assert account["guardianStatus"] == "approved" and "approvalCode" not in account
    assert get_user_by_id(child)["approvalCode"] is None  # used up


def test_declining_needs_the_code_too(client):
    registered = register_child(client)
    child, code = registered["userId"], registered["approvalCode"]
    guardian = new_user("699000001", "guardian")
    assert approve(client, guardian, child, wrong(code), action="decline").status_code == 400
    assert get_user_by_id(child)["guardianStatus"] == "pending"
    assert approve(client, guardian, child, code, action="decline").status_code == 200
    assert get_user_by_id(child)["guardianStatus"] == "declined"


def test_five_wrong_codes_stop_the_code_until_the_child_gets_a_new_one(client):
    registered = register_child(client)
    child, code = registered["userId"], registered["approvalCode"]
    guardian = new_user("699000001", "guardian")

    for _ in range(4):
        assert "doesn't match" in approve(client, guardian, child, wrong(code)).get_json()["message"]
    fifth = approve(client, guardian, child, wrong(code)).get_json()["message"]
    assert "New code" in fifth
    # Now even the right code doesn't work, and the child's page says what happened
    refused = approve(client, guardian, child, code)
    assert refused.status_code == 400 and "new code" in refused.get_json()["message"]
    account = me(client, child)
    assert account["approvalCode"] is None and account["approvalCodeBlocked"] is True

    new = client.post("/me/approval-code", headers=auth_header(child, "seller"))
    assert new.status_code == 200
    new_code = new.get_json()["approvalCode"]
    assert me(client, child)["approvalCode"] == new_code and me(client, child)["approvalCodeBlocked"] is False
    assert approve(client, guardian, child, new_code).status_code == 200


def test_only_a_child_waiting_for_approval_can_get_a_new_code(client):
    adult = new_user("677000001", "seller")
    assert client.post("/me/approval-code", headers=auth_header(adult, "seller")).status_code == 403
    assert client.post("/me/approval-code").status_code == 401

    registered = register_child(client)
    child = registered["userId"]
    approve(client, new_user("699000001", "guardian"), child, registered["approvalCode"])
    assert client.post("/me/approval-code", headers=auth_header(child, "seller")).status_code == 403


def test_children_from_before_codes_get_one_when_they_open_their_page(client):
    # Registered before approval codes existed: no code saved
    child = create_user("+237677000010", "password123", "Junior", "seller",
                        guardian={"name": "Mama Junior", "phone": "+237699000001", "relation": "mother"})
    guardian = new_user("699000001", "guardian")
    waiting = approve(client, guardian, child, "000000")
    assert waiting.status_code == 400 and "open Africycle" in waiting.get_json()["message"]

    code = me(client, child)["approvalCode"]
    assert len(code) == 6 and me(client, child)["approvalCode"] == code  # the same code each time
    assert approve(client, guardian, child, code).status_code == 200


# ---- New admins wait for an existing admin's approval ----

def register_admin(client, phone, name):
    response = client.post("/register", json={"name": name, "phoneNumber": phone,
                                              "password": "secret123", "role": "admin"})
    assert response.status_code == 201, response.get_json()
    return response.get_json()["userId"]


def login(client, phone, code=None):
    body = {"phoneNumber": phone, "password": "secret123"}
    if code is not None:
        body["code"] = code
    return client.post("/login", json=body)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def full_admin(client, phone, name):
    """Registers the first admin and turns on two-step login: a token that opens everything."""
    register_admin(client, phone, name)
    token = login(client, phone).get_json()["token"]
    secret = client.post("/admin/two-step/setup", headers=bearer(token)).get_json()["secret"]
    response = client.post("/admin/two-step/enable", headers=bearer(token),
                           json={"code": totp.code_at(secret, totp.current_step())})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["token"]


def test_the_first_admin_is_approved_and_later_ones_wait(client, monkeypatch):
    monkeypatch.setattr(Config, "ADMIN_PHONE_NUMBERS", [ADMIN_PHONE, SECOND_ADMIN])
    ada = full_admin(client, ADMIN_PHONE, "Ada")
    assert client.get("/admin/stats", headers=bearer(ada)).status_code == 200

    bob = register_admin(client, SECOND_ADMIN, "Bob")
    response = login(client, SECOND_ADMIN)
    assert response.status_code == 200  # Bob can log in, but no admin tool opens
    bob_token = response.get_json()["token"]
    for path, method in (("/admin/stats", "get"), ("/admin/users", "get"), ("/admin/actions", "get"),
                         ("/admin/two-step/setup", "post"), ("/admin/two-step/enable", "post"),
                         (f"/admin/flag-account/{bob}", "post"), ("/admin/guide-recordings", "post")):
        answer = getattr(client, method)(path, headers=bearer(bob_token), json={})
        assert answer.status_code == 403 and answer.get_json()["code"] == "admin_approval", path

    users = client.get("/admin/users", headers=bearer(ada)).get_json()["users"]
    assert {u["name"]: bool(u["adminApproved"]) for u in users} == {"Ada": True, "Bob": False}

    assert client.post(f"/admin/approve-admin/{bob}", headers=bearer(ada)).status_code == 200
    assert client.post("/admin/two-step/setup", headers=bearer(bob_token)).status_code == 200
    log = client.get("/admin/actions", headers=bearer(ada)).get_json()["actions"]
    assert (log[0]["action"], log[0]["adminName"], log[0]["targetName"]) == ("admin_approved", "Ada", "Bob")


def test_an_admin_waiting_for_approval_can_be_flagged(client, monkeypatch):
    monkeypatch.setattr(Config, "ADMIN_PHONE_NUMBERS", [ADMIN_PHONE, SECOND_ADMIN])
    ada = full_admin(client, ADMIN_PHONE, "Ada")
    stranger = register_admin(client, SECOND_ADMIN, "Not really Bob")
    assert client.post(f"/admin/flag-account/{stranger}", headers=bearer(ada),
                       json={"reason": "Not one of us"}).status_code == 200
    assert login(client, SECOND_ADMIN).status_code == 403  # suspended
    assert client.post(f"/admin/approve-admin/{stranger}", headers=bearer(ada)).status_code == 404


def test_only_a_waiting_admin_account_can_be_approved(client):
    admin = new_user(ADMIN_PHONE, "admin", "Ada")
    seller = new_user("677000001", "seller")
    headers = auth_header(admin, "admin")
    for target in (seller, admin, 999):
        assert client.post(f"/admin/approve-admin/{target}", headers=headers).status_code == 404
    waiting = new_user(SECOND_ADMIN, "admin", "Bob")
    assert client.post(f"/admin/approve-admin/{waiting}").status_code == 401
    assert client.post(f"/admin/approve-admin/{waiting}",
                       headers=auth_header(seller, "seller")).status_code == 401


def test_the_admin_page_warns_when_the_login_secret_is_short(client, monkeypatch):
    admin = new_user(ADMIN_PHONE, "admin", "Ada")
    monkeypatch.setattr(Config, "SECRET_KEY", "short-secret")
    assert client.get("/admin/stats", headers=auth_header(admin, "admin")).get_json()["weakSecret"] is True
    monkeypatch.setattr(Config, "SECRET_KEY", "k3Jx9" * 8)  # 40 characters
    assert client.get("/admin/stats", headers=auth_header(admin, "admin")).get_json()["weakSecret"] is False
    assert make_token(admin, "admin")  # tokens still work with the new secret
