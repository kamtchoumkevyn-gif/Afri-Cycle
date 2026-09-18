import pytest
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.db import init_db, DB_PATH
from models.user import create_user
from models.notification import (
    create_notification,
    get_notification_by_id,
    update_location,
    update_status,
)

@pytest.fixture(autouse=True)
def fresh_database():
    """Run before every test: wipes and rebuilds a clean database."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    yield
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        
def test_create_notification_return_id():
    # We need real seller and buyer user ids first, since notifications
    # reference them via foreign keys.
    seller_id = create_user("677100001", "password123", "seller")
    buyer_id =  create_user("677100002", "password123", "buyer")
    
    notification_id = create_notification(seller_id, buyer_id, material_category_id=1)
    
    assert notification_id is not None
    assert notification_id > 0
    
def test_new_notification_starts_pending():
    seller_id = create_user("677100003", "password123", "seller") 
    buyer_id = create_user("677100004", "password123", "buyer")
    
    notification_id = create_notification(seller_id, buyer_id, material_category_id=1)
    notification = get_notification_by_id(notification_id)
    
    assert notification["status"] == "pending"
    
def test_update_loaction_changes_coordinates():
    seller_id = create_user("677100005", "password123", "seller")
    buyer_id = create_user("677100006", "password123", "buyer")
    
    notification_id = create_notification(seller_id, buyer_id, material_category_id=1)
    update_location(notification_id, 4.0511, 9.7679)
    
    notification = get_notification_by_id(notification_id)
    assert notification["sellerLatitude"] == 4.0511
    assert notification["sellerLongitude"] == 9.7679
    
def test_update_status_to_valid_value():
    seller_id = create_user("677100007", "password123", "seller")
    buyer_id = create_user("677100008", "password123", "buyer")
    
    notification_id = create_notification(seller_id, buyer_id, material_category_id=1)
    update_status(notification_id, "in transit") 
    
    notification = get_notification_by_id(notification_id)
    assert notification["status"] == "in transit"
    
def test_update_status_rejects_invalid_value():
    seller_id = create_user("677100009", "password123", "seller")
    buyer_id = create_user("677100010", "password123", "buyer")
    
    notification_id = create_notification(seller_id, buyer_id, material_category_id=1)
    
    # "flying" is not a real status, this should raise an error,
    # nir silently save bad data.
    with pytest.raises(ValueError):
        update_status(notification_id, "flying")                      