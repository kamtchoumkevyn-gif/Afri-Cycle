import pytest
import os
import sys




# Add the parent folder (backend) to the Python path
# So that we can import from database folder and models folder
# this test file lives inside tests folder

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.db import init_db, DB_PATH
from models.user import  create_user, find_user_by_phone, verify_login

# This is a "fixture" - a setup function that runs before each test. It initializes the database.
@pytest.fixture(autouse=True)
def fresh_database():
    """Runs before each every test: wipes and rebuilds a clean database."""
    
    # If an old database file exists from a previous test run, delete it.
    #This prevents leftover data (like duplicated phone numbers) from
    # causing tests to fail unexpectedly.
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        
    # Recreate the database from scratch
    init_db()
    
    #Yield hands control over the test code function .
    #Everything below yeild runs AFTER the test finishes (cleanup).
    yield
    
    #Clean up again after the test, so no test data leaks into
    #the next test or gets accidentally committed to your project.
    if os.path.exists(DB_PATH):
       os.remove(DB_PATH)
       
def test_create_user_return_id():
    #Create a new seller account.
    user_id = create_user("677000001","mypassword123", "seller")
    
    # A successful creation should return a real database ID,
    #not None , and IDs always start from 1 upward.
    assert user_id is not None
    assert user_id > 0
    
def test_find_user_by_phone_after_creation():
    # First, create a buyer account.
    create_user("677000002","mypassword123","buyer")
    
    # Then look them up by theier phone number.
    user = find_user_by_phone("677000002")
    
    #Confirm the user was found, and their stored data matches
    # what we originally saved.
    assert user is not None
    assert user["phoneNumber"]== "677000002"
    assert user["role"]== "buyer" 
                
def test_find_user_by_phone_not_found():
    # Searching for a phone number that was never registered 
    # should return None, not crash or return random data.
    user = find_user_by_phone("000000000")
    assert user is None
    
def test_verify_login_corect_password():
    #Create an account with a known password.
    create_user("677000003", "correctpassword", "seller")
    
    #Try logging in with the SAME password used at registration.
    user = verify_login("677000003", "correctpassword")
    
    #Login should succeed and return  the user's data.
    assert user is not None
    
def test_verify_login_wrong_password():
    #Create an account with a known password.
    create_user("677000004", "correctpassword", "seller")
    
    #Try logging in with an INCORRECT password
    user = verify_login("677000004", "wrongpassword")
    
    #Login must fail and return None, this is the core security
    # check that protects user accunts.
    assert user is None
    
def test_verify_login_nonexistent_user():
    #Try logging in with a phone number that was never registered.
    user = verify_login("999999999", "anypassword")
    
    #Should safely retuen None instaed of crashing.
    assert user is None
    
    
    
    
    
    