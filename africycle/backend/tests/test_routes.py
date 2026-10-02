from helpers import auth_header, new_user, new_category, new_buyer_with_profile
from models.notification import create_notification


# ---- Auth ----

def register(client, phone="677000001", role="seller", password="password123", name="Paul"):
    return client.post("/register", json={
        "name": name, "phoneNumber": phone, "password": password, "role": role
    })


def test_register_success(client):
    assert register(client).status_code == 201


def test_register_duplicate_fails(client):
    register(client)
    assert register(client).status_code == 400


def test_register_missing_fields_fails(client):
    assert client.post("/register", json={"phoneNumber": "677000001"}).status_code == 400


def test_register_admin_requires_whitelisted_phone(client):
    assert register(client, phone="677000001", role="admin").status_code == 403
    assert register(client, phone="699999999", role="admin").status_code == 201


def test_login_returns_token_and_role(client):
    register(client, role="buyer")
    response = client.post("/login", json={"phoneNumber": "677000001", "password": "password123"})
    data = response.get_json()
    assert response.status_code == 200
    assert data["token"] and data["role"] == "buyer"


def test_login_with_wrong_role_is_rejected(client):
    register(client, role="buyer")
    response = client.post("/login", json={
        "phoneNumber": "677000001", "password": "password123", "role": "seller"
    })
    assert response.status_code == 403


def test_both_account_can_enter_as_buyer(client):
    register(client, role="both")
    response = client.post("/login", json={
        "phoneNumber": "677000001", "password": "password123", "role": "buyer"
    })
    assert response.status_code == 200


def test_register_rejects_unknown_role_and_short_password(client):
    assert register(client, role="king").status_code == 400
    assert register(client, password="123").status_code == 400


def test_login_wrong_password_fails(client):
    register(client)
    response = client.post("/login", json={"phoneNumber": "677000001", "password": "nope"})
    assert response.status_code == 401


def test_login_nonexistent_user_fails(client):
    response = client.post("/login", json={"phoneNumber": "000", "password": "x"})
    assert response.status_code == 401


# ---- Buyer ----

def test_buyer_routes_require_auth(client):
    assert client.get("/buyer/prices").status_code == 401
    assert client.post("/buyer/set-price", json={}).status_code == 401


def test_seller_cannot_use_buyer_routes(client):
    seller = new_user("677000001", "seller")
    assert client.get("/buyer/prices", headers=auth_header(seller, "seller")).status_code == 401


def test_buyer_set_and_list_prices(client):
    buyer = new_user("677000002", "buyer")
    category = new_category()
    headers = auth_header(buyer, "buyer")
    client.post("/buyer/set-price", json={"materialCategoryId": category, "pricePerKg": 150}, headers=headers)
    client.post("/buyer/set-price", json={"materialCategoryId": category, "pricePerKg": 200}, headers=headers)
    prices = client.get("/buyer/prices", headers=headers).get_json()["prices"]
    assert len(prices) == 1
    assert prices[0]["pricePerKg"] == 200
    assert prices[0]["materialName"] == "Scrap Iron"


def test_buyer_save_and_update_profile(client):
    buyer = new_user("677000002", "buyer")
    headers = auth_header(buyer, "buyer")
    assert client.post("/buyer/profile", json={}, headers=headers).status_code == 400
    client.post("/buyer/profile", json={"latitude": 4.05, "longitude": 9.7, "workingHours": "8-18"}, headers=headers)
    client.post("/buyer/profile", json={"latitude": 4.1, "longitude": 9.8}, headers=headers)
    profile = client.get("/buyer/profile", headers=headers).get_json()["profile"]
    assert (profile["latitude"], profile["workingHours"]) == (4.1, "8-18")


def test_buyer_log_transaction_and_history(client):
    buyer = new_user("677000002", "buyer")
    seller = new_user("677000001", "seller", "Jean")
    category = new_category()
    headers = auth_header(buyer, "buyer")

    bad = client.post("/buyer/log-transaction", json={"sellerId": seller}, headers=headers)
    assert bad.status_code == 400

    ok = client.post("/buyer/log-transaction", json={
        "sellerId": seller, "materialCategoryId": category, "weightKg": 10, "pricePerKg": 150
    }, headers=headers)
    assert ok.status_code == 201

    history = client.get("/buyer/transaction-history", headers=headers).get_json()["transactions"]
    assert len(history) == 1
    assert history[0]["totalAmount"] == 1500
    assert history[0]["sellerName"] == "Jean"


# ---- Seller ----

def test_nearby_buyers_sorted_by_price_and_radius(client):
    seller = new_user("677000001", "seller")
    category = new_category()
    new_buyer_with_profile("677000002", 4.0500, 9.7000, 100, category, "Cheap")
    new_buyer_with_profile("677000003", 4.0510, 9.7010, 200, category, "Best")
    new_buyer_with_profile("677000004", 6.0500, 9.7000, 999, category, "Far")

    response = client.get(
        f"/seller/nearby-buyers?lat=4.05&lng=9.70&materialCategoryId={category}",
        headers=auth_header(seller, "seller")
    )
    buyers = response.get_json()["buyers"]
    assert [b["buyerName"] for b in buyers] == ["Best", "Cheap"]


def test_nearby_buyers_requires_location(client):
    seller = new_user("677000001", "seller")
    response = client.get("/seller/nearby-buyers", headers=auth_header(seller, "seller"))
    assert response.status_code == 400


def test_buyer_profile_view_and_contact(client):
    seller = new_user("677000001", "seller")
    category = new_category()
    buyer = new_buyer_with_profile("677000002", 4.05, 9.70, 150, category)
    headers = auth_header(seller, "seller")

    profile = client.get(f"/seller/buyer-profile/{buyer}", headers=headers).get_json()
    assert profile["prices"][0]["materialName"] == "Scrap Iron"
    assert client.get("/seller/buyer-profile/9999", headers=headers).status_code == 404

    contact = client.get(f"/seller/contact-buyer/{buyer}", headers=headers).get_json()
    assert contact["phoneNumber"] == "677000002"


def test_notify_buyer(client):
    seller = new_user("677000001", "seller")
    category = new_category()
    buyer = new_buyer_with_profile("677000002", 4.05, 9.70, 150, category)
    headers = auth_header(seller, "seller")

    assert client.post("/seller/notify-buyer", json={"buyerId": buyer}, headers=headers).status_code == 400
    response = client.post("/seller/notify-buyer",
                           json={"buyerId": buyer, "materialCategoryId": category}, headers=headers)
    assert response.status_code == 201
    assert "notificationId" in response.get_json()


# ---- Notifications ----

def test_notifications_listed_for_each_side(client):
    seller = new_user("677000001", "seller", "Jean")
    buyer = new_user("677000002", "buyer", "Marie")
    category = new_category()
    create_notification(seller, buyer, category)

    for user_id, role in ((seller, "seller"), (buyer, "buyer")):
        rows = client.get("/notifications", headers=auth_header(user_id, role)).get_json()["notifications"]
        assert len(rows) == 1
        assert rows[0]["sellerName"] == "Jean" and rows[0]["buyerName"] == "Marie"


def test_only_sender_can_update_location(client):
    seller = new_user("677000001", "seller")
    buyer = new_user("677000002", "buyer")
    nid = create_notification(seller, buyer, new_category())
    body = {"latitude": 4.06, "longitude": 9.71}

    assert client.patch(f"/notifications/{nid}/location", json=body,
                        headers=auth_header(buyer, "buyer")).status_code == 403
    assert client.patch(f"/notifications/{nid}/location", json=body,
                        headers=auth_header(seller, "seller")).status_code == 200


def test_status_update_validates(client):
    seller = new_user("677000001", "seller")
    buyer = new_user("677000002", "buyer")
    nid = create_notification(seller, buyer, new_category())
    headers = auth_header(seller, "seller")

    assert client.patch(f"/notifications/{nid}/status", json={"status": "flying"},
                        headers=headers).status_code == 400
    assert client.patch(f"/notifications/{nid}/status", json={"status": "in transit"},
                        headers=headers).status_code == 200

    outsider = new_user("677000009", "buyer")
    assert client.patch(f"/notifications/{nid}/status", json={"status": "arrived"},
                        headers=auth_header(outsider, "buyer")).status_code == 403


# ---- Admin ----

def test_admin_routes_reject_non_admins(client):
    seller = new_user("677000001", "seller")
    assert client.get("/admin/stats", headers=auth_header(seller, "seller")).status_code == 401


def test_admin_stats_and_activity(client):
    admin = new_user("699999999", "admin")
    new_user("677000001", "seller")
    new_user("677000002", "buyer")
    headers = auth_header(admin, "admin")

    stats = client.get("/admin/stats", headers=headers).get_json()
    assert (stats["totalUsers"], stats["sellerCount"], stats["buyerCount"]) == (3, 1, 1)

    activity = client.get("/admin/activity-stats", headers=headers)
    assert activity.status_code == 200


def test_admin_flag_and_unflag(client):
    admin = new_user("699999999", "admin")
    seller = new_user("677000001", "seller")
    headers = auth_header(admin, "admin")

    client.post(f"/admin/flag-account/{seller}", json={"reason": "Suspicious volume"}, headers=headers)
    flagged = client.get("/admin/flagged-accounts", headers=headers).get_json()["flaggedAccounts"]
    assert flagged[0]["reason"] == "Suspicious volume"

    client.post(f"/admin/unflag-account/{seller}", headers=headers)
    assert client.get("/admin/flagged-accounts", headers=headers).get_json()["flaggedAccounts"] == []

    assert client.post("/admin/flag-account/9999", headers=headers).status_code == 404


# ---- Chat ----

def test_chat_send_and_read(client):
    seller = new_user("677000001", "seller", "Jean")
    buyer = new_user("677000002", "buyer", "Marie")

    sent = client.post("/chat/send", json={"receiverId": buyer, "messageText": "On my way"},
                       headers=auth_header(seller, "seller"))
    assert sent.status_code == 201

    thread = client.get(f"/chat/messages/{seller}", headers=auth_header(buyer, "buyer")).get_json()
    assert thread["otherUserName"] == "Jean"
    assert thread["messages"][0]["messageText"] == "On my way"

    convos = client.get("/chat/conversations", headers=auth_header(buyer, "buyer")).get_json()
    assert convos["conversations"][0]["otherUserName"] == "Jean"


def test_chat_rejects_bad_messages(client):
    seller = new_user("677000001", "seller")
    headers = auth_header(seller, "seller")
    assert client.post("/chat/send", json={"receiverId": seller, "messageText": "hi"},
                       headers=headers).status_code == 400
    assert client.post("/chat/send", json={"receiverId": 9999, "messageText": "hi"},
                       headers=headers).status_code == 404
    assert client.post("/chat/send", json={"receiverId": 2, "messageText": "   "},
                       headers=headers).status_code == 400


# ---- Materials & frontend serving ----

def test_material_categories_listed(client):
    user = new_user("677000001", "seller")
    new_category("Plastic")
    data = client.get("/material-categories", headers=auth_header(user, "seller")).get_json()
    assert [c["name"] for c in data["categories"]] == ["Plastic"]


def test_frontend_is_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/login.html").status_code == 200
