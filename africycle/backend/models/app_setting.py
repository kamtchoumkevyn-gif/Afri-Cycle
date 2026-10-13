from database.db import get_connection


def get_setting(name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM app_settings WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else None


def get_or_create_setting(name, make_value):
    """Returns the stored value, creating it with make_value() the first time.
    Safe when several server processes start at once: the first one to save wins,
    and every process then uses that same value."""
    value = get_setting(name)
    if value is not None:
        return value
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO app_settings (name, value) VALUES (?, ?) ON CONFLICT (name) DO NOTHING",
        (name, make_value())
    )
    conn.commit()
    conn.close()
    return get_setting(name)
