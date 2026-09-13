from flask import Flask
from flask_cors import CORS
from routes.auth_routes import auth_bp, limiter

# Create the main Flask application object.
# This is the "app" that test_auth_routes.py is trying to import.
app = Flask(__name__)


# A llow requests from your frontend (running on a different port)
# to reach this backend, without CORS blocking them.
CORS(app)
limiter.init_app(app)

#Register the auth routes (register/login) onto the main app.
# This connects everything we build in auth_routes.py to real URLs.
app.register_blueprint(auth_bp)

# This block only if you start the app directly with "python app.py"
# It won't run when pytest imports "app" for testing.
if __name__ == '__main__':
    app.run(debug=True, port=500)
    
