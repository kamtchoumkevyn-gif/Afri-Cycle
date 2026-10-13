"""Maps, material photos (tap to say "I'm coming"), and guardian-supervised child accounts."""
import base64

import database.db as db
from helpers import auth_header, new_buyer_with_profile, new_category, new_user
from models.buyer_price import set_price
from models.chat import send_message
from models.notification import create_notification, get_notification_by_id
from models.transaction import create_transaction

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def data_url(raw, mime="image/png"):
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def upload(client, buyer, category, photo):
    return client.post("/buyer/material-photo", json={"materialCategoryId": category, "photo": photo},
                       headers=auth_header(buyer, "buyer"))


# ---- Material photos ----

def test_buyer_must_set_a_price_before_adding_a_photo(client):
    buyer = new_user("677000002", "buyer")
    category = new_category()
    assert upload(client, buyer, category, data_url(TINY_PNG)).status_code == 400
    set_price(buyer, category, 150)
    assert upload(client, buyer, category, data_url(TINY_PNG)).status_code == 201


def test_photo_appears_with_the_price_and_can_be_viewed(client):
    buyer = new_user("677000002", "buyer")
    category = new_category()
    set_price(buyer, category, 150)
    photo_id = upload(client, buyer, category, data_url(TINY_PNG)).get_json()["photoId"]

    prices = client.get("/buyer/prices", headers=auth_header(buyer, "buyer")).get_json()["prices"]
    assert prices[0]["photoId"] == photo_id

    seller = new_user("677000001", "seller")
    image = client.get(f"/photos/{photo_id}", headers=auth_header(seller, "seller"))
    assert image.status_code == 200
    assert image.mimetype == "image/png"
    assert image.data == TINY_PNG
    assert client.get(f"/photos/{photo_id}").status_code == 401  # login required


def test_photo_upload_rejects_non_images_and_oversized_files(client):
    buyer = new_user("677000002", "buyer")
    category = new_category()
    set_price(buyer, category, 150)
    for bad in ("not a data url",
                data_url(b"hello", "text/plain"),
                data_url(TINY_PNG, "image/jpeg"),          # PNG bytes labelled as JPEG
                data_url(b"\xff\xd8\xff" + b"0" * 400_001, "image/jpeg"),
                "data:image/png;base64,@@@@"):
        assert upload(client, buyer, category, bad).status_code == 400, bad[:40]


def test_replacing_a_photo_gives_it_a_new_id_and_it_can_be_removed(client):
    buyer = new_user("677000002", "buyer")
    category = new_category()
    set_price(buyer, category, 150)
    first = upload(client, buyer, category, data_url(TINY_PNG)).get_json()["photoId"]
    second = upload(client, buyer, category, data_url(b"\xff\xd8\xff\xe0jpeg", "image/jpeg")).get_json()["photoId"]
    assert second != first
    headers = auth_header(buyer, "buyer")
    assert client.delete(f"/buyer/material-photo/{category}", headers=headers).status_code == 200
    assert client.delete(f"/buyer/material-photo/{category}", headers=headers).status_code == 404


def test_seller_sees_the_buyers_photos_in_their_profile(client):
    category = new_category()
    buyer = new_buyer_with_profile("677000002", 4.05, 9.70, 200, category, name="Marie")
    photo_id = upload(client, buyer, category, data_url(TINY_PNG)).get_json()["photoId"]
    seller = new_user("677000001", "seller")
    profile = client.get(f"/seller/buyer-profile/{buyer}", headers=auth_header(seller, "seller")).get_json()
    assert profile["prices"][0]["photoId"] == photo_id


# ---- Tapping a photo tells the buyer the seller is coming ----

def test_tapping_a_photo_starts_a_trip_in_transit(client):
    category = new_category()
    buyer = new_buyer_with_profile("677000002", 4.05, 9.70, 200, category)
    seller = new_user("677000001", "seller")
    body = {"buyerId": buyer, "materialCategoryId": category, "onTheWay": True}

    first = client.post("/seller/notify-buyer", json=body, headers=auth_header(seller, "seller"))
    assert first.status_code == 201 and first.get_json()["status"] == "in transit"

    again = client.post("/seller/notify-buyer", json=body, headers=auth_header(seller, "seller"))
    assert again.status_code == 200  # a double tap reuses the same trip
    assert again.get_json()["notificationId"] == first.get_json()["notificationId"]

    seen = client.get("/notifications", headers=auth_header(buyer, "buyer")).get_json()["notifications"]
    assert len(seen) == 1 and seen[0]["status"] == "in transit"


def test_photo_tap_moves_a_pending_trip_to_in_transit(client):
    category = new_category()
    buyer = new_buyer_with_profile("677000002", 4.05, 9.70, 200, category)
    seller = new_user("677000001", "seller")
    nid = create_notification(seller, buyer, category)
    response = client.post("/seller/notify-buyer", json={
        "buyerId": buyer, "materialCategoryId": category, "onTheWay": True
    }, headers=auth_header(seller, "seller"))
    assert response.get_json()["notificationId"] == nid
    assert get_notification_by_id(nid)["status"] == "in transit"


def test_notify_checks_the_buyer_and_material_exist(client):
    category = new_category()
    seller = new_user("677000001", "seller")
    other_seller = new_user("677000003", "seller")
    headers = auth_header(seller, "seller")
    assert client.post("/seller/notify-buyer", json={"buyerId": 9999, "materialCategoryId": category},
                       headers=headers).status_code == 404
    assert client.post("/seller/notify-buyer", json={"buyerId": other_seller, "materialCategoryId": category},
                       headers=headers).status_code == 404
    buyer = new_user("677000002", "buyer")
    assert client.post("/seller/notify-buyer", json={"buyerId": buyer, "materialCategoryId": 9999},
                       headers=headers).status_code == 404


# ---- Map data ----

def test_nearby_buyers_include_their_coordinates(client):
    category = new_category()
    new_buyer_with_profile("677000002", 4.05, 9.70, 200, category)
    seller = new_user("677000001", "seller")
    buyers = client.get(f"/seller/nearby-buyers?lat=4.06&lng=9.71&materialCategoryId={category}",
                        headers=auth_header(seller, "seller")).get_json()["buyers"]
    assert (buyers[0]["latitude"], buyers[0]["longitude"]) == (4.05, 9.70)


def test_seller_location_updates_are_timestamped(client):
    category = new_category()
    buyer = new_buyer_with_profile("677000002", 4.05, 9.70, 200, category)
    seller = new_user("677000001", "seller")
    nid = create_notification(seller, buyer, category, status="in transit")
    client.patch(f"/notifications/{nid}/location", json={"latitude": 4.06, "longitude": 9.71},
                 headers=auth_header(seller, "seller"))
    row = client.get("/notifications", headers=auth_header(buyer, "buyer")).get_json()["notifications"][0]
    assert row["sellerLatitude"] == 4.06 and row["locationUpdatedAt"]


# ---- Children and guardians ----

def register_child(client, phone="677000010", guardian_phone="699000001", **overrides):
    body = {"name": "Junior", "phoneNumber": phone, "password": "password123", "role": "seller",
            "isMinor": True, "guardianName": "Mama Junior", "guardianPhone": guardian_phone,
            "guardianRelation": "mother"}
    body.update(overrides)
    return client.post("/register", json=body)


def login_id(client, phone, role):
    response = client.post("/login", json={"phoneNumber": phone, "password": "password123", "role": role})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["userId"]


def test_child_registration_needs_full_guardian_details(client):
    assert register_child(client, guardianName="").status_code == 400
    assert register_child(client, guardianPhone="123").status_code == 400
    assert register_child(client, guardianPhone="677000010").status_code == 400  # same as the child
    assert register_child(client, guardianRelation="friend").status_code == 400
    assert register_child(client, role="buyer").status_code == 400                # children only sell
    response = register_child(client)
    assert response.status_code == 201 and "guardian" in response.get_json()["message"]


def test_child_cannot_trade_or_message_until_approved(client):
    register_child(client)
    child = login_id(client, "677000010", "seller")
    headers = auth_header(child, "seller")
    blocked = client.get("/seller/nearby-buyers?lat=4.05&lng=9.7", headers=headers)
    assert blocked.status_code == 403
    assert blocked.get_json()["code"] == "guardian_approval_required"
    buyer = new_user("677000002", "buyer")
    assert client.post("/chat/send", json={"receiverId": buyer, "messageText": "hi"},
                       headers=headers).status_code == 403


def test_only_the_named_guardian_can_approve(client):
    register_child(client, guardian_phone="699000001")
    child = login_id(client, "677000010", "seller")

    stranger = new_user("699000002", "buyer")
    assert client.get("/guardian/children", headers=auth_header(stranger, "buyer")).get_json()["pending"] == []
    assert client.post(f"/guardian/children/{child}/approve",
                       headers=auth_header(stranger, "buyer")).status_code == 404

    client.post("/register", json={"name": "Mama Junior", "phoneNumber": "+237 699 000 001",
                                   "password": "password123", "role": "guardian"})
    guardian = login_id(client, "699000001", "guardian")
    pending = client.get("/guardian/children", headers=auth_header(guardian, "guardian")).get_json()["pending"]
    assert [c["id"] for c in pending] == [child]

    assert client.post(f"/guardian/children/{child}/approve",
                       headers=auth_header(guardian, "guardian")).status_code == 200
    assert client.get("/seller/nearby-buyers?lat=4.05&lng=9.7",
                      headers=auth_header(child, "seller")).status_code == 200
    children = client.get("/guardian/children", headers=auth_header(guardian, "guardian")).get_json()
    assert children["pending"] == [] and [c["id"] for c in children["children"]] == [child]


def test_a_parent_with_a_buyer_account_can_supervise(client):
    register_child(client, guardian_phone="699000001")
    child = login_id(client, "677000010", "seller")
    parent = new_user("699000001", "buyer")
    assert client.post(f"/guardian/children/{child}/approve",
                       headers=auth_header(parent, "buyer")).status_code == 200


def test_declined_child_stays_blocked(client):
    register_child(client, guardian_phone="699000001")
    child = login_id(client, "677000010", "seller")
    guardian = new_user("699000001", "guardian")
    assert client.post(f"/guardian/children/{child}/decline",
                       headers=auth_header(guardian, "guardian")).status_code == 200
    response = client.get("/seller/nearby-buyers?lat=4.05&lng=9.7", headers=auth_header(child, "seller"))
    assert response.status_code == 403 and "declined" in response.get_json()["message"]


def test_guardian_sees_the_childs_deliveries_sales_and_messages(client):
    register_child(client, guardian_phone="699000001")
    child = login_id(client, "677000010", "seller")
    guardian = new_user("699000001", "guardian")
    client.post(f"/guardian/children/{child}/approve", headers=auth_header(guardian, "guardian"))

    category = new_category()
    buyer = new_buyer_with_profile("677000002", 4.05, 9.70, 200, category, name="Marie")
    create_notification(child, buyer, category, status="in transit")
    create_transaction(child, buyer, category, 10, 200)
    send_message(buyer, child, "Come before 5pm")

    activity = client.get(f"/guardian/children/{child}/activity", headers=auth_header(guardian, "guardian"))
    data = activity.get_json()
    assert activity.status_code == 200
    assert data["deliveries"][0]["buyerName"] == "Marie"
    assert data["sales"][0]["totalAmount"] == 2000
    assert data["conversations"][0]["otherUserName"] == "Marie"

    thread = client.get(f"/guardian/children/{child}/messages/{buyer}",
                        headers=auth_header(guardian, "guardian")).get_json()
    assert thread["messages"][0]["messageText"] == "Come before 5pm"

    stranger = new_user("699000002", "guardian")
    assert client.get(f"/guardian/children/{child}/activity",
                      headers=auth_header(stranger, "guardian")).status_code == 404


def test_buyers_are_told_a_seller_is_under_18(client):
    register_child(client, guardian_phone="699000001")
    child = login_id(client, "677000010", "seller")
    category = new_category()
    buyer = new_buyer_with_profile("677000002", 4.05, 9.70, 200, category)
    create_notification(child, buyer, category)
    row = client.get("/notifications", headers=auth_header(buyer, "buyer")).get_json()["notifications"][0]
    assert row["sellerIsMinor"]
    thread = client.get(f"/chat/messages/{child}", headers=auth_header(buyer, "buyer")).get_json()
    assert thread["otherIsMinor"] is True


def test_me_reports_guardian_status_and_children(client):
    register_child(client, guardian_phone="699000001")
    child = login_id(client, "677000010", "seller")
    me = client.get("/me", headers=auth_header(child, "seller")).get_json()
    assert me["isMinor"] and me["guardianStatus"] == "pending" and me["guardianName"] == "Mama Junior"
    guardian = new_user("699000001", "guardian")
    assert client.get("/me", headers=auth_header(guardian, "guardian")).get_json()["childrenCount"] == 1
    assert client.get("/me").status_code == 401


# ---- Upgrading an existing database ----

def test_init_db_upgrades_a_database_made_before_these_features(tmp_path, monkeypatch):
    # Rebuild the tables as earlier releases made them (the live Neon database
    # looks like this): no material_photos table and none of ADDED_COLUMNS.
    # Runs on SQLite, or on Postgres when TEST_DATABASE_URL is set.
    if not db.using_postgres():
        monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "old.db"))
    conn = db.get_connection()
    cursor = conn.cursor()
    for table in reversed(db.TABLES):
        cursor.execute(f"DROP TABLE IF EXISTS {table}")
    for statement in db.SCHEMA[:db.FIRST_RELEASE_TABLE_COUNT]:
        cursor.execute(statement)
    cursor.execute("INSERT INTO users (phoneNumber, passwordHash, name, role) "
                   "VALUES ('677000001', 'x', 'Old', 'seller')")
    cursor.execute("INSERT INTO users (phoneNumber, passwordHash, name, role) "
                   "VALUES ('677000002', 'x', 'Old buyer', 'buyer')")
    cursor.execute("INSERT INTO chat_messages (senderId, receiverId, messageText, createdAt) "
                   "VALUES (2, 1, 'Sent before read receipts existed', '2026-10-01T09:00:00')")
    conn.commit()
    conn.close()

    db.init_db()
    db.init_db()  # running twice must be harmless

    conn = db.get_connection()
    cursor = conn.cursor()
    for table, columns in db.ADDED_COLUMNS.items():
        assert {column[0] for column in columns} <= db._column_names(cursor, table)
    cursor.execute("SELECT name, isMinor, guardianStatus FROM users")
    old_user = cursor.fetchone()
    assert old_user["name"] == "Old"
    assert old_user["isMinor"] == 0  # existing accounts are adults
    assert old_user["guardianStatus"] is None
    cursor.execute("SELECT readAt FROM chat_messages")
    assert cursor.fetchone()["readAt"] == "2026-10-01T09:00:00"  # old messages don't show up as unread
    for table in db.TABLES[db.FIRST_RELEASE_TABLE_COUNT:]:  # photos, notifications, settings
        cursor.execute(f"SELECT COUNT(*) AS n FROM {table}")
        assert cursor.fetchone()["n"] == 0, table
    conn.close()
