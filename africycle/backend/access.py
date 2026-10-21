"""Who may see or reach whom.

Buyers with a buying point are public: any seller can find them, see their prices and
phone number, and message them. Everyone else (sellers, under-18 sellers, guardians,
admins) is visible only to the people they deal with: the other side of a trip or a
purchase, or someone they already exchanged messages with. An account that isn't
reachable answers like a missing one, so changing a number in a request reveals
nothing about other accounts (tests/test_access.py).

Each check uses one database connection, since every connection to the hosted
database costs a round trip.
"""
from database.db import get_connection

PUBLIC_BUYER = """
    SELECT u.id FROM users u JOIN buyer_profile bp ON bp.userId = u.id
    WHERE u.id = ? AND u.role IN ('buyer', 'both') AND COALESCE(u.isFlagged, 0) = 0
"""

# A trip or a purchase between the two (either one selling), or a message either way
LINKS = (
    "SELECT id FROM notifications WHERE (sellerId = ? AND buyerId = ?) OR (sellerId = ? AND buyerId = ?) LIMIT 1",
    "SELECT id FROM transactions WHERE (sellerId = ? AND buyerId = ?) OR (sellerId = ? AND buyerId = ?) LIMIT 1",
    "SELECT id FROM chat_messages WHERE (senderId = ? AND receiverId = ?) OR (senderId = ? AND receiverId = ?) LIMIT 1",
)


def account_id(value):
    """value as an account id if it is a whole number (not true/false or text), else None."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _found(query, params):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone() is not None
    finally:
        conn.close()


def is_public_buyer(user_id):
    """A buyer (or buyer-and-seller) with a buying point whose account isn't suspended."""
    user_id = account_id(user_id)
    return user_id is not None and _found(PUBLIC_BUYER, (user_id,))


def may_contact(user_id, other_id):
    """Whether user_id may see other_id's name and exchange messages with them: other_id
    is a public buyer, or the two share a trip, a purchase or a conversation."""
    other_id = account_id(other_id)
    if other_id is None or other_id == user_id:
        return False
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(PUBLIC_BUYER, (other_id,))
        if cursor.fetchone() is not None:
            return True
        for query in LINKS:
            cursor.execute(query, (user_id, other_id, other_id, user_id))
            if cursor.fetchone() is not None:
                return True
        return False
    finally:
        conn.close()


def came_to(seller_id, buyer_id):
    """Whether the seller told this buyer they were bringing material (a trip), which a
    recorded purchase needs: a receipt names a seller who really came."""
    return _found("SELECT id FROM notifications WHERE sellerId = ? AND buyerId = ? LIMIT 1",
                  (seller_id, buyer_id))
