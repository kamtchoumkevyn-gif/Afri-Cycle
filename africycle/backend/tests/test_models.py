import pytest
from helpers import new_user, new_category
from models.user import find_user_by_phone, verify_login
from models.notification import (
    create_notification, get_notification_by_id, get_notifications_for_buyer,
    get_notifications_for_seller, update_location, update_status, delete_notification
)
from models.transaction import (
    create_transaction, get_transaction_by_id,
    get_transactions_by_buyer, get_transactions_by_seller
)
from models.buyer_price import (
    set_price, get_price_by_id, get_prices_by_buyer,
    get_price_for_buyer_and_category, delete_price
)
from models.buyer_profile import (
    create_buyer_profile, get_buyer_profile_by_user_id,
    update_buyer_location, update_working_hours, delete_buyer_profile
)
from models.material_category import (
    get_category_by_id, get_category_by_name, get_all_categories,
    update_reference_photo, delete_category, seed_default_categories
)
from models.chat import (
    send_message, get_message_by_id, get_conversation,
    get_conversations_for_user, delete_message
)


@pytest.fixture
def seller_buyer_category():
    seller = new_user("677000001", "seller", "Seller")
    buyer = new_user("677000002", "buyer", "Buyer")
    category = new_category()
    return seller, buyer, category


# ---- User ----

def test_create_and_find_user():
    user_id = new_user("677000001", "seller")
    user = find_user_by_phone("677000001")
    assert user["id"] == user_id
    assert user["passwordHash"] != "password123"


def test_find_user_not_found():
    assert find_user_by_phone("000") is None


def test_verify_login_correct_and_wrong_password():
    new_user("677000001", "seller")
    assert verify_login("677000001", "password123") is not None
    assert verify_login("677000001", "wrong") is None
    assert verify_login("000", "password123") is None


# ---- Notification ----

def test_notification_starts_pending(seller_buyer_category):
    seller, buyer, category = seller_buyer_category
    nid = create_notification(seller, buyer, category)
    assert get_notification_by_id(nid)["status"] == "pending"


def test_notifications_listed_per_side(seller_buyer_category):
    seller, buyer, category = seller_buyer_category
    create_notification(seller, buyer, category)
    assert len(get_notifications_for_buyer(buyer)) == 1
    assert len(get_notifications_for_seller(seller)) == 1
    assert get_notifications_for_buyer(seller) == []


def test_notification_location_and_status(seller_buyer_category):
    seller, buyer, category = seller_buyer_category
    nid = create_notification(seller, buyer, category)
    update_location(nid, 4.06, 9.71)
    update_status(nid, "in transit")
    n = get_notification_by_id(nid)
    assert (n["sellerLatitude"], n["sellerLongitude"], n["status"]) == (4.06, 9.71, "in transit")


def test_notification_rejects_invalid_status(seller_buyer_category):
    seller, buyer, category = seller_buyer_category
    nid = create_notification(seller, buyer, category)
    with pytest.raises(ValueError):
        update_status(nid, "teleported")


def test_delete_notification(seller_buyer_category):
    seller, buyer, category = seller_buyer_category
    nid = create_notification(seller, buyer, category)
    delete_notification(nid)
    assert get_notification_by_id(nid) is None


# ---- Transaction ----

def test_transaction_total_is_computed(seller_buyer_category):
    seller, buyer, category = seller_buyer_category
    tid = create_transaction(seller, buyer, category, 10, 150)
    assert get_transaction_by_id(tid)["totalAmount"] == 1500


def test_transactions_filtered_by_party(seller_buyer_category):
    seller, buyer, category = seller_buyer_category
    other_buyer = new_user("677000003", "buyer")
    create_transaction(seller, buyer, category, 10, 150)
    create_transaction(seller, other_buyer, category, 5, 150)
    assert len(get_transactions_by_buyer(buyer)) == 1
    assert len(get_transactions_by_seller(seller)) == 2


def test_transaction_not_found():
    assert get_transaction_by_id(9999) is None


# ---- Buyer price ----

def test_set_price_upserts(seller_buyer_category):
    _, buyer, category = seller_buyer_category
    first = set_price(buyer, category, 150)
    second = set_price(buyer, category, 200)
    assert first == second
    prices = get_prices_by_buyer(buyer)
    assert len(prices) == 1 and prices[0]["pricePerKg"] == 200


def test_price_lookup_and_delete(seller_buyer_category):
    _, buyer, category = seller_buyer_category
    pid = set_price(buyer, category, 150)
    assert get_price_for_buyer_and_category(buyer, category)["pricePerKg"] == 150
    delete_price(pid)
    assert get_price_by_id(pid) is None


# ---- Buyer profile ----

def test_buyer_profile_lifecycle():
    buyer = new_user("677000002", "buyer")
    create_buyer_profile(buyer, 4.05, 9.70, "8am-6pm")
    update_buyer_location(buyer, 4.10, 9.75)
    update_working_hours(buyer, "9am-5pm")
    profile = get_buyer_profile_by_user_id(buyer)
    assert (profile["latitude"], profile["longitude"], profile["workingHours"]) == (4.10, 9.75, "9am-5pm")
    delete_buyer_profile(buyer)
    assert get_buyer_profile_by_user_id(buyer) is None


# ---- Material category ----

def test_categories_sorted_and_searchable():
    new_category("Scrap Iron")
    new_category("Banana Peels")
    names = [c["name"] for c in get_all_categories()]
    assert names == ["Banana Peels", "Scrap Iron"]
    assert get_category_by_name("Scrap Iron") is not None
    assert get_category_by_name("Gold") is None


def test_category_update_and_delete():
    cid = new_category()
    update_reference_photo(cid, "http://example.com/new.jpg")
    assert get_category_by_id(cid)["referencePhotoUrl"] == "http://example.com/new.jpg"
    delete_category(cid)
    assert get_category_by_id(cid) is None


def test_seed_only_runs_on_empty_table():
    seed_default_categories()
    seed_default_categories()
    assert len(get_all_categories()) == 4


# ---- Chat ----

def test_chat_conversation_both_directions(seller_buyer_category):
    seller, buyer, _ = seller_buyer_category
    send_message(seller, buyer, "I'm 10 minutes away")
    send_message(buyer, seller, "Okay, I'll wait")
    thread = get_conversation(seller, buyer)
    assert [m["messageText"] for m in thread] == ["I'm 10 minutes away", "Okay, I'll wait"]


def test_chat_conversation_list_and_delete(seller_buyer_category):
    seller, buyer, _ = seller_buyer_category
    mid = send_message(seller, buyer, "Hello")
    convos = get_conversations_for_user(seller)
    assert convos[0]["otherUserId"] == buyer
    delete_message(mid)
    assert get_message_by_id(mid) is None
