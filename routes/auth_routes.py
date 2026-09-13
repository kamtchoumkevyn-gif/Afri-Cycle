from flask import Blueprint, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import jwt
import datetime 
import os
from dotenv import load_dotenv
from models.user import create_user, verify_login

# Load variables from the .env file (like JWT_SECRET_KEY) into the environment.

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


# A "Blueprint" is Flask's way of grouping related routed together,
# here, everything related to authentification ( register, login).
auth_bp = Blueprint('auth', __name__)

# Read the secret key from the environment, NEVER hard-code it.
# This key is used to sin tokens, if it leaks, attackers could forge logins.
SECRET_KEY = os.getenv("JWT_SECRET_KEY")


# Rate liliter: tracks request by IP address, to slow down brute-force
# password-guessing attacks against /login.
limiter = Limiter(key_func=get_remote_address)

@auth_bp.route('/register', methods=['POST'])
def register():
    #Get the JSON data sent by the frontend are present.
    #If any are missing, reject the request immediately with 400.
    data = request.get_json()
    phone_number = data.get('phoneNumber')
    password = data.get('password')
    role = data.get('role')
    
    if not phone_number or not password or not role:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    
    # Try creating the user. If the phone number already exists,
    # create_user() will raise an exception (since phoneNumber is UNIQUE).
    try:
        user_id = create_user(phone_number, password, role)
        return jsonify({"success": True, "userId": user_id}), 201
    except Exception as e:
        return jsonify({"success": False, "error": "phone number already registered"}),400
    
@auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute") # Blocks more that login attempts per IP
def login():
    data = request.get_json()
    phone_number = data.get('phoneNumber')
    password = data.get('password')
    
    
    # Check the phone number + password combo using the function
    # we already built and tested in user.py.
    user = verify_login(phone_number, password)
    if user is None:
        # Same error for "wrong passwor" and "user doesn't exist"
        # this avoides revealing to attackers with phone numbers are registered.
        return jsonify({"success": False, "error": "Invalid phone numberor password"}),401
    now = datetime.datetime.now(datetime.timezone.utc)
    token = jwt.encode({
        "userId": user["id"],
        "role": user["role"],
        "iat": now,
        "exp": now + datetime.timedelta(days=7)
    }, SECRET_KEY, algorithm="HS256")
    
    return jsonify({"success": True, "token": token, "role": user["role"] }), 200
   