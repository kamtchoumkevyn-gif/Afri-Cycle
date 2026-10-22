"""Who may see or reach whom: every request is tried as the wrong person.

Buyers with a buying point are public: sellers find them, see their prices and number,
and message them. Everyone else (sellers, under-18 sellers, guardians, admins) is only
visible to the people they deal with: the other side of a trip or a purchase, or
someone they already exchanged messages with. Changing a number in a request must
never reveal anything about another account.
"""
import re

from app import app as flask_app
from database.db import get_connection
from helpers import auth_header, new_buyer_with_profile, new_category, new_user
from models.notification import create_notification

LAT, LNG = 4.05, 9.70


def flag(user_id):
    conn = get_connection()
    conn.cursor().execute("UPDATE users SET isFlagged = 1, flagReason = 'test' WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def approved_child(client, phone="677000010", guardian_phone="699000001"):
    """An under-18 seller whose guardian approved the account: (child id, guardian id)."""
    response = client.post("/register", json={
        "name": "Junior", "phoneNumber": phone, "password": "password123", "role": "seller",
        "isMinor": True, "guardianName": "Mama Junior", "guardianPhone": guardian_phone,
        "guardianRelation": "mother"})
    assert response.status_code == 201, response.get_json()
    child = client.post("/login", json={"phoneNumber": phone, "password": "password123",
                                        "role": "seller"}).get_json()["userId"]
    guardian = new_user(guardian_phone, "guardian", "Mama Junior")
    code = client.get("/me", headers=auth_header(child, "seller")).get_json()["approvalCode"]
    assert client.post(f"/guardian/children/{child}/approve", json={"code": code},
                       headers=auth_header(guardian, "guardian")).status_code == 200
    return child, guardian


def send(client, sender, role, receiver, text="Hello"):
    return client.post("/chat/send", json={"receiverId": receiver, "messageText": text},
                       headers=auth_header(sender, role))


# ---- Phone numbers and profiles: only buyers' are public ----

def test_sellers_get_only_public_buyers_numbers(client):
    category = new_category()
    buyer = new_buyer_with_profile("677000002", LAT, LNG, 150, category)
    seller = new_user("677000001", "seller", "Jean")
    other_seller = new_user("677000003", "seller", "Paul")
    admin = new_user("699999999", "admin", "Admin")
    no_point = new_user("677000004", "buyer", "Buyer without a buying point")
    child, guardian = approved_child(client)
    headers = auth_header(seller, "seller")

    shown = client.get(f"/seller/contact-buyer/{buyer}", headers=headers)
    assert shown.status_code == 200 and shown.get_json()["phoneNumber"] == "+237677000002"
    for private in (other_seller, admin, no_point, child, guardian, 999999):
        response = client.get(f"/seller/contact-buyer/{private}", headers=headers)
        assert response.status_code == 404, private
        assert "phoneNumber" not in response.get_json()
        assert client.get(f"/seller/buyer-profile/{private}", headers=headers).status_code == 404, private


def test_a_suspended_buyer_disappears_from_sellers_view(client):
    category = new_category()
    open_buyer = new_buyer_with_profile("677000002", LAT, LNG, 150, category, name="Open")
    suspended = new_buyer_with_profile("677000005", LAT, LNG, 300, category, name="Suspended")
    flag(suspended)
    seller = new_user("677000001", "seller")
    headers = auth_header(seller, "seller")

    nearby = client.get(f"/seller/nearby-buyers?lat={LAT}&lng={LNG}", headers=headers).get_json()["buyers"]
    assert [b["buyerId"] for b in nearby] == [open_buyer]
    assert client.get(f"/seller/buyer-profile/{suspended}", headers=headers).status_code == 404
    assert client.get(f"/seller/contact-buyer/{suspended}", headers=headers).status_code == 404
    notify = client.post("/seller/notify-buyer", json={"buyerId": suspended, "materialCategoryId": category},
                         headers=headers)
    assert notify.status_code == 404


def test_odd_ids_are_refused_without_a_server_error(client):
    category = new_category()
    seller = new_user("677000001", "seller")
    headers = auth_header(seller, "seller")
    for odd in ("2", "abc", True, 2.5, None, [2]):
        notify = client.post("/seller/notify-buyer", json={"buyerId": odd, "materialCategoryId": category},
                             headers=headers)
        assert notify.status_code in (400, 404), odd
        assert send(client, seller, "seller", odd).status_code in (400, 404), odd


# ---- Messages: only between people who deal with each other ----

def test_anyone_can_write_to_a_public_buyer_and_the_buyer_can_answer(client):
    category = new_category()
    buyer = new_buyer_with_profile("677000002", LAT, LNG, 150, category, name="Marie")
    seller = new_user("677000001", "seller", "Jean")
    assert send(client, seller, "seller", buyer).status_code == 201
    thread = client.get(f"/chat/messages/{seller}", headers=auth_header(buyer, "buyer"))
    assert thread.status_code == 200 and thread.get_json()["otherUserName"] == "Jean"
    assert send(client, buyer, "buyer", seller, "Come at 3").status_code == 201


def test_a_buyer_writes_to_a_seller_only_after_the_seller_came_or_wrote(client):
    category = new_category()
    buyer = new_buyer_with_profile("677000002", LAT, LNG, 150, category, name="Marie")
    seller = new_user("677000001", "seller", "Jean")
    stranger_buyer = new_buyer_with_profile("677000006", LAT, LNG, 120, category, name="Stranger")
    create_notification(seller_id=seller, buyer_id=buyer, material_category_id=category)

    assert send(client, buyer, "buyer", seller).status_code == 201       # the seller is coming to her
    refused = send(client, stranger_buyer, "buyer", seller)                 # never dealt with him
    assert refused.status_code == 404
    hidden = client.get(f"/chat/messages/{seller}", headers=auth_header(stranger_buyer, "buyer"))
    assert hidden.status_code == 404
    assert "otherUserName" not in hidden.get_json() and "otherIsMinor" not in hidden.get_json()


def test_strangers_cannot_reach_or_see_a_child(client):
    category = new_category()
    child, _guardian = approved_child(client)
    adult_seller = new_user("677000001", "seller", "Jean")
    stranger_buyer = new_buyer_with_profile("677000006", LAT, LNG, 120, category, name="Stranger")
    for stranger, role in ((adult_seller, "seller"), (stranger_buyer, "buyer")):
        assert send(client, stranger, role, child).status_code == 404
        hidden = client.get(f"/chat/messages/{child}", headers=auth_header(stranger, role))
        assert hidden.status_code == 404 and "otherIsMinor" not in hidden.get_json()

    # The buyer the child chose to sell to can answer, and sees the Under 18 notice
    buyer = new_buyer_with_profile("677000002", LAT, LNG, 150, category, name="Marie")
    assert send(client, child, "seller", buyer, "I am coming").status_code == 201
    thread = client.get(f"/chat/messages/{child}", headers=auth_header(buyer, "buyer")).get_json()
    assert thread["otherIsMinor"] is True
    assert send(client, buyer, "buyer", child, "OK").status_code == 201


def test_nobody_can_look_up_admins_or_guardians_through_messages(client):
    category = new_category()
    buyer = new_buyer_with_profile("677000002", LAT, LNG, 150, category)
    admin = new_user("699999999", "admin", "Admin")
    guardian = new_user("699000001", "guardian", "Mama")
    for other in (admin, guardian, 999999):
        assert client.get(f"/chat/messages/{other}", headers=auth_header(buyer, "buyer")).status_code == 404
        assert send(client, buyer, "buyer", other).status_code == 404


# ---- Receipts name only a seller who really came ----

def test_a_buyer_records_a_purchase_only_from_a_seller_who_came_to_them(client):
    category = new_category()
    buyer = new_buyer_with_profile("677000002", LAT, LNG, 150, category)
    seller = new_user("677000001", "seller", "Jean")
    other_seller = new_user("677000003", "seller", "Paul")
    create_notification(seller_id=seller, buyer_id=buyer, material_category_id=category)
    body = {"materialCategoryId": category, "weightKg": 10, "pricePerKg": 150}

    refused = client.post("/buyer/log-transaction", json={**body, "sellerId": other_seller},
                          headers=auth_header(buyer, "buyer"))
    assert refused.status_code == 400
    assert client.get("/seller/sales", headers=auth_header(other_seller, "seller")).get_json()["sales"] == []
    recorded = client.post("/buyer/log-transaction", json={**body, "sellerId": seller},
                           headers=auth_header(buyer, "buyer"))
    assert recorded.status_code == 201


def test_no_purchase_from_a_suspended_seller(client):
    category = new_category()
    buyer = new_buyer_with_profile("677000002", LAT, LNG, 150, category)
    seller = new_user("677000001", "seller", "Jean")
    create_notification(seller_id=seller, buyer_id=buyer, material_category_id=category)
    flag(seller)
    response = client.post("/buyer/log-transaction", json={
        "sellerId": seller, "materialCategoryId": category, "weightKg": 10, "pricePerKg": 150
    }, headers=auth_header(buyer, "buyer"))
    assert response.status_code == 400


# ---- Trips, photos and children's pages ----

def test_only_the_two_sides_see_or_change_a_trip(client):
    category = new_category()
    buyer = new_buyer_with_profile("677000002", LAT, LNG, 150, category)
    seller = new_user("677000001", "seller")
    outsider = new_buyer_with_profile("677000006", LAT, LNG, 120, category)
    trip = create_notification(seller_id=seller, buyer_id=buyer, material_category_id=category)
    headers = auth_header(outsider, "buyer")
    assert client.get(f"/notifications/{trip}", headers=headers).status_code == 403
    assert client.patch(f"/notifications/{trip}/status", json={"status": "completed"},
                        headers=headers).status_code == 403
    assert client.patch(f"/notifications/{trip}/location", json={"latitude": 4, "longitude": 9},
                        headers=headers).status_code == 403
    assert client.get("/notifications", headers=headers).get_json()["notifications"] == []
    assert client.get(f"/notifications/{trip}", headers=auth_header(buyer, "buyer")).status_code == 200


def test_a_buyer_cannot_remove_another_buyers_material_photo(client):
    category = new_category()
    owner = new_buyer_with_profile("677000002", LAT, LNG, 150, category)
    other = new_buyer_with_profile("677000006", LAT, LNG, 120, category)
    png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    saved = client.post("/buyer/material-photo", json={"materialCategoryId": category, "photo": png},
                        headers=auth_header(owner, "buyer"))
    assert saved.status_code == 201
    assert client.delete(f"/buyer/material-photo/{category}", headers=auth_header(other, "buyer")).status_code == 404
    photo = saved.get_json()["photoId"]
    assert client.get(f"/photos/{photo}", headers=auth_header(other, "buyer")).status_code == 200


def test_the_waiting_list_shows_only_the_end_of_a_childs_number(client):
    """Numbers aren't confirmed, so whoever registers the guardian's number sees the
    waiting child's name, but not the child's whole phone number."""
    client.post("/register", json={
        "name": "Junior", "phoneNumber": "677000010", "password": "password123", "role": "seller",
        "isMinor": True, "guardianName": "Mama Junior", "guardianPhone": "699000001",
        "guardianRelation": "mother"})
    guardian = new_user("699000001", "guardian", "Mama Junior")
    pending = client.get("/guardian/children", headers=auth_header(guardian, "guardian")).get_json()["pending"]
    assert len(pending) == 1
    assert "phoneNumber" not in pending[0] and pending[0]["phoneEnd"] == "10"


def test_another_guardian_sees_nothing_of_a_child(client):
    category = new_category()
    child, guardian = approved_child(client)
    other_guardian = new_user("699000002", "guardian", "Someone else")
    buyer = new_buyer_with_profile("677000002", LAT, LNG, 150, category)
    send(client, child, "seller", buyer, "I am coming")
    headers = auth_header(other_guardian, "guardian")
    assert client.get(f"/guardian/children/{child}/activity", headers=headers).status_code == 404
    assert client.get(f"/guardian/children/{child}/messages/{buyer}", headers=headers).status_code == 404

    # The real guardian reads the child's real conversations, and nobody else's names
    own = auth_header(guardian, "guardian")
    assert client.get(f"/guardian/children/{child}/messages/{buyer}", headers=own).status_code == 200
    stranger = new_user("677000003", "seller", "Paul")
    hidden = client.get(f"/guardian/children/{child}/messages/{stranger}", headers=own)
    assert hidden.status_code == 404 and "otherUserName" not in hidden.get_json()


# ---- Every route: a login first, and every id checked ----

# Routes anyone may use without logging in
PUBLIC = {
    "serve_index", "serve_frontend", "serve_asset_links", "serve_service_worker", "download_android_app",
    "health", "ping", "auth_bp.login", "auth_bp.register", "material_bp.list_categories",
    "guide_bp.recording_audio", "guide_bp.recorded_languages", "guide_bp.recordings_for",
}

# Every route that takes an id, and the rule that protects it (tested above, in
# test_receipts, test_admin_security, test_approvals, test_features and test_routes).
# A new route with an id fails test_every_route_with_an_id_has_a_rule until it is added
# here, with a test that tries it as the wrong person.
ID_RULES = {
    "admin_bp.approve_admin_account": "approved admins with the two-step code",
    "admin_bp.flag_account": "approved admins with the two-step code",
    "admin_bp.unflag_account": "approved admins with the two-step code",
    "admin_bp.two_step_reset": "approved admins with the two-step code",
    "guide_bp.remove_recording": "approved admins with the two-step code",
    "guide_bp.recording_audio": "public: the voice guide's recordings",
    "buyer_bp.remove_material_photo": "the buyer's own photo only",
    "buyer_bp.material_photo": "logged in: buyers' photos of materials are shown to sellers",
    "chat_bp.messages": "people who deal with each other",
    "guardian_bp.child_activity": "the child's approved guardian",
    "guardian_bp.approve_child": "the guardian's number plus the code on the child's phone",
    "guardian_bp.decline_child": "the guardian's number plus the code on the child's phone",
    "guardian_bp.child_messages": "the child's approved guardian, for the child's real conversations",
    "notification_bp.get_notification": "the two sides of the trip",
    "notification_bp.update_notification_location": "the seller of the trip",
    "notification_bp.update_notification_status": "the two sides of the trip",
    "receipt_bp.receipt_photo": "the two sides of the purchase, the child's guardian, admins with the code",
    "receipt_bp.show_receipt": "the two sides of the purchase, the child's guardian, admins with the code",
    "receipt_bp.add_receipt_photo": "the buyer who recorded the purchase",
    "receipt_bp.remove_receipt_photo": "the buyer who recorded the purchase, photos of that receipt only",
    "seller_bp.buyer_profile_view": "public buyers only",
    "seller_bp.contact_buyer": "public buyers only",
}


def sample_url(rule):
    url = re.sub(r"<int:\w+>", "1", rule.rule)
    return re.sub(r"<language>", "fr", url)


def test_every_private_route_needs_a_login(client):
    checked = 0
    for rule in flask_app.url_map.iter_rules():
        if rule.endpoint in PUBLIC or rule.endpoint == "static":
            continue
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            response = client.open(sample_url(rule), method=method, json={})
            assert response.status_code == 401, (method, rule.rule, response.status_code)
            checked += 1
    assert checked > 40


def test_every_route_with_an_id_has_a_rule():
    with_ids = {rule.endpoint for rule in flask_app.url_map.iter_rules() if "<int:" in rule.rule}
    assert with_ids == set(ID_RULES), (
        "Add each new route with an id to ID_RULES, with a test that tries it as the wrong person")
