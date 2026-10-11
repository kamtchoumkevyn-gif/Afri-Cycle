import os
import sys
import tempfile

# Must run before the app is imported: point everything at a throwaway database
TEST_DB = os.path.join(tempfile.gettempdir(), "africycle_test.db")
os.environ["AFRICYCLE_DB_PATH"] = TEST_DB
os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_PHONE_NUMBERS"] = "699999999"

# Tests wipe the database, so they must never reach the real one. DATABASE_URL is
# set to "" here (which .env can't override) unless you deliberately point the
# suite at a throwaway Postgres database:
#   TEST_DATABASE_URL=postgresql://user:pass@localhost/africycle_test pytest
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest  # noqa: E402
from app import app as flask_app  # noqa: E402
from database.db import init_db, reset_db, using_postgres  # noqa: E402
from extensions import limiter  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    if using_postgres():
        reset_db()
    else:
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        init_db()
    limiter.reset()  # every test starts with a clean rate-limit counter
    yield
    if not using_postgres() and os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    flask_app.config["RATELIMIT_ENABLED"] = False
    return flask_app.test_client()
