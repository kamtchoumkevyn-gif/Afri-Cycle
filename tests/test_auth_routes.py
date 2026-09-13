

import pytest
import os
import sys



# Add the parent folder (backend) to python's search path,
# so we can import app.py, database folder, and models folder from here,
# evev though thid test file lives inside tests folder
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app import app # We import theactual Flask app object
from database.db import init_db, DB_PATH

@pytest.fixture(autouse=True)
def fresh_database():
    """Runs before every test: wipes and rebuilds a clean database."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    yield
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        
@pytest.fixture
def client():
    """
    Flask's test client lets us send fake HTTP request (like POST /register)
    directly to our app in tests, without needing running server.
    """
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client
      
def test_register_seller_success(client):
    #Send a POST request to /register with seller dat,
    #exactly lie a real frontend form would.
    response = client.post('/register', json={
       "phoneNumber": "677111111",
       "password": "mypassword123",
       "role": "seller"
   })        
                
#A successful registration confirm success and include a user id
    assert response.status_code == 201
    
#The response body should confirm success and include a user id
    data = response.get_json()
    assert data["success"] is True
    assert "userId" in data
    
def test_register_duplicate_phone_fails(client):
    #Register a user once, successfully.
    client.post('/register', json={
        "phoneNumber": "677222222",
        "password": "mypassword123",
        "role": "buyer"
    })    
    
    #Try registering AGAIN with the same phone number.
    response = client.post('/register', json={
        "phoneNumber": "677222222",
        "password": "anotherpassword",
        "role": "buyer"
    })
    
    #This should fail, since phone numbers must be unique.
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    
def test_register_missing_fields_fails(client):
    #Send an incomplete request, missing the password field entirely.
    response = client.post('/register', json={
        "phoneNumber": "677333333",
        "role": "seller"
    })    
    # Should be rejected with a 400 Bad Request, not crash the server.
    assert response.status_code == 400
    
def test_login_success(client):
    #First, register a user.
    response = client.post('/register', json={
        "phoneNumber": "677444444",
        "password": "correctpassword",
        "role": "seller"
    })    
    # Then log in wih the correct credentials.
    response = client.post('/login', json={
        "phoneNumber": "677444444",
        "password": "correctpassword"
    })
    
    
    # A successful login should return 200 OK and a token.
    assert response.status_code ==200
    data = response.get_json()
    assert data["success"] is True
    assert "token" in data
    
def test_login_wrong_password_fails(client):
    #Register a user.
    response = client.post('/register', json={
        "phoneNumber": "677555555",
        "password": "correctpassword",
        "role": "buyer"
    })    
    #Attempt login with the WRONG password.
    response = client.post('/login', json={
        "phoneNumber": "677555555",
        "password": "wrongpassword"
    })
    # Should be rejected with 401 Unauthorized.
    assert response.status_code == 401
    
def test_login_nonexistent_user_fails(client):
    #Try logging in with a phone number that never registered.
    response = client.post('/login', json={
        "phoneNumber": "999999999",
        "password": "anypassword"
        
    })    
    # Should also return 401, same as wrong password
    #(we don't want to reveal WHETHER a phone number exists, for security).
    assert response.status_code == 401
