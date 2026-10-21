"""Receipts: a buyer records a purchase, takes photos of the material for its receipt,
and both sides of the sale (and an under-18 seller's guardian) can see it."""
import base64

from helpers import auth_header, came_by, new_category, new_user

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
TINY_JPEG = b"\xff\xd8\xff\xe0" + b"jpeg data"


def data_url(raw, mime="image/png"):
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def record_purchase(client, buyer, seller, category, weight=10, price=150):
    """The seller comes to the buyer (a trip), then the buyer records the purchase."""
    came_by(seller, buyer, category)
    response = client.post("/buyer/log-transaction", json={
        "sellerId": seller, "materialCategoryId": category, "weightKg": weight, "pricePerKg": price
    }, headers=auth_header(buyer, "buyer"))
    assert response.status_code == 201, response.get_json()
    return response.get_json()["transactionId"]


def add_photo(client, buyer, receipt, raw=TINY_PNG, mime="image/png", role="buyer"):
    return client.post(f"/receipts/{receipt}/photos", json={"photo": data_url(raw, mime)},
                       headers=auth_header(buyer, role))


def people():
    buyer = new_user("677000002", "buyer", "Marie")
    seller = new_user("677000001", "seller", "Jean")
    category = new_category("Scrap Iron")
    return buyer, seller, category


def test_the_buyer_adds_photos_to_the_receipt_and_everyone_on_it_sees_them(client):
    buyer, seller, category = people()
    receipt = record_purchase(client, buyer, seller, category, weight=12.5, price=150)
    first = add_photo(client, buyer, receipt)
    assert first.status_code == 201
    second = add_photo(client, buyer, receipt, TINY_JPEG, "image/jpeg")
    assert second.status_code == 201

    shown = client.get(f"/receipts/{receipt}", headers=auth_header(buyer, "buyer")).get_json()["receipt"]
    assert shown["photoIds"] == [first.get_json()["photoId"], second.get_json()["photoId"]]
    assert (shown["buyerName"], shown["sellerName"], shown["materialName"]) == ("Marie", "Jean", "Scrap Iron")
    assert (shown["weightKg"], shown["pricePerKg"], shown["totalAmount"]) == (12.5, 150, 1875)
    assert shown["canAddPhotos"] is True and shown["maxPhotos"] == 3

    # The seller sees the same receipt, but only the buyer changes its photos
    for_seller = client.get(f"/receipts/{receipt}", headers=auth_header(seller, "seller")).get_json()["receipt"]
    assert for_seller["photoIds"] == shown["photoIds"] and for_seller["canAddPhotos"] is False
    image = client.get(f"/receipt-photos/{shown['photoIds'][0]}", headers=auth_header(seller, "seller"))
    assert image.status_code == 200 and image.mimetype == "image/png" and image.data == TINY_PNG
    assert "private" in image.headers["Cache-Control"]
    assert add_photo(client, seller, receipt, role="seller").status_code == 403


def test_a_receipt_keeps_three_photos_at_most_and_the_buyer_can_remove_one(client):
    buyer, seller, category = people()
    receipt = record_purchase(client, buyer, seller, category)
    ids = [add_photo(client, buyer, receipt).get_json()["photoId"] for _ in range(3)]
    full = add_photo(client, buyer, receipt)
    assert full.status_code == 400 and "3" in full.get_json()["message"]

    headers = auth_header(buyer, "buyer")
    assert client.delete(f"/receipts/{receipt}/photos/{ids[1]}", headers=headers).status_code == 200
    assert client.delete(f"/receipts/{receipt}/photos/{ids[1]}", headers=headers).status_code == 404
    assert add_photo(client, buyer, receipt).status_code == 201  # room again
    shown = client.get(f"/receipts/{receipt}", headers=headers).get_json()["receipt"]
    assert len(shown["photoIds"]) == 3 and ids[1] not in shown["photoIds"]


def test_only_real_photos_go_on_a_receipt(client):
    buyer, seller, category = people()
    receipt = record_purchase(client, buyer, seller, category)
    headers = auth_header(buyer, "buyer")
    for bad in ("not a data url", data_url(b"hello", "text/plain"), data_url(TINY_PNG, "image/jpeg"),
                data_url(b"\xff\xd8\xff" + b"0" * 400_001, "image/jpeg"), None, 12):
        response = client.post(f"/receipts/{receipt}/photos", json={"photo": bad}, headers=headers)
        assert response.status_code == 400, str(bad)[:40]
    assert client.post(f"/receipts/{receipt}/photos", data="nonsense", headers=headers).status_code == 400


def test_strangers_cannot_see_a_receipt_or_its_photos(client):
    buyer, seller, category = people()
    receipt = record_purchase(client, buyer, seller, category)
    photo = add_photo(client, buyer, receipt).get_json()["photoId"]
    stranger = new_user("677000009", "buyer", "Other buyer")
    other_seller = new_user("677000008", "seller", "Other seller")
    for user, role in ((stranger, "buyer"), (other_seller, "seller")):
        headers = auth_header(user, role)
        # Answered like a receipt that doesn't exist, so ids reveal nothing
        assert client.get(f"/receipts/{receipt}", headers=headers).status_code == 404
        assert client.get(f"/receipt-photos/{photo}", headers=headers).status_code == 404
        assert client.post(f"/receipts/{receipt}/photos", json={"photo": data_url(TINY_PNG)},
                           headers=headers).status_code == 404
        assert client.delete(f"/receipts/{receipt}/photos/{photo}", headers=headers).status_code == 404
    assert client.get(f"/receipts/{receipt}").status_code == 401
    assert client.get(f"/receipt-photos/{photo}").status_code == 401
    assert client.get("/receipts/999", headers=auth_header(buyer, "buyer")).status_code == 404
    admin = new_user("699999999", "admin", "Admin")
    assert client.get(f"/receipts/{receipt}", headers=auth_header(admin, "admin")).status_code == 200


def test_a_guardian_sees_the_receipts_of_their_childs_sales(client):
    buyer, _seller, category = people()
    registered = client.post("/register", json={
        "name": "Awa", "phoneNumber": "677000010", "password": "password123", "role": "seller",
        "isMinor": True, "guardianName": "Mama Awa", "guardianPhone": "699000001", "guardianRelation": "mother"})
    assert registered.status_code == 201
    child = client.post("/login", json={"phoneNumber": "677000010", "password": "password123",
                                        "role": "seller"}).get_json()["userId"]
    guardian = new_user("699000001", "guardian", "Mama Awa")
    headers = auth_header(guardian, "guardian")
    code = registered.get_json()["approvalCode"]
    assert client.post(f"/guardian/children/{child}/approve", headers=headers, json={"code": code}).status_code == 200
    receipt = record_purchase(client, buyer, child, category)
    add_photo(client, buyer, receipt)

    shown = client.get(f"/receipts/{receipt}", headers=headers)
    assert shown.status_code == 200 and len(shown.get_json()["receipt"]["photoIds"]) == 1
    photo = shown.get_json()["receipt"]["photoIds"][0]
    assert client.get(f"/receipt-photos/{photo}", headers=headers).status_code == 200
    sales = client.get(f"/guardian/children/{child}/activity", headers=headers).get_json()["sales"]
    assert sales[0]["photoCount"] == 1
    # Another adult is not that child's guardian
    other = new_user("677000007", "guardian", "Someone else")
    assert client.get(f"/receipts/{receipt}", headers=auth_header(other, "guardian")).status_code == 404


def test_lists_of_purchases_and_sales_count_the_photos(client):
    buyer, seller, category = people()
    first = record_purchase(client, buyer, seller, category, weight=5)
    record_purchase(client, buyer, seller, category, weight=7)
    add_photo(client, buyer, first)
    add_photo(client, buyer, first)

    history = client.get("/buyer/transaction-history", headers=auth_header(buyer, "buyer")).get_json()["transactions"]
    assert sorted(row["photoCount"] for row in history) == [0, 2]

    sales = client.get("/seller/sales", headers=auth_header(seller, "seller"))
    assert sales.status_code == 200
    rows = sales.get_json()["sales"]
    assert [row["buyerName"] for row in rows] == ["Marie", "Marie"]
    assert sorted(row["photoCount"] for row in rows) == [0, 2]
    assert {row["materialName"] for row in rows} == {"Scrap Iron"}
    assert client.get("/seller/sales", headers=auth_header(buyer, "buyer")).status_code == 401
    assert client.get("/seller/sales").status_code == 401


def test_a_purchase_names_a_real_collector_and_material(client):
    buyer, seller, category = people()
    other_buyer = new_user("677000003", "buyer", "Not a seller")
    came_by(seller, buyer, category)
    headers = auth_header(buyer, "buyer")
    for seller_id, material in ((9999, category), (seller, 9999), (other_buyer, category), (buyer, category),
                                (str(seller), category), (seller, str(category)), (True, category)):
        response = client.post("/buyer/log-transaction", json={
            "sellerId": seller_id, "materialCategoryId": material, "weightKg": 10, "pricePerKg": 150
        }, headers=headers)
        assert response.status_code == 400, (seller_id, material)
    both = new_user("677000004", "both", "Buys and sells")
    assert record_purchase(client, buyer, both, category)
