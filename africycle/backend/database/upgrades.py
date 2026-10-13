"""Changes to data already saved, made once each when the app starts after an update.

init_db runs the ones not done yet, in order, and records each in app_settings (as
"upgrade:<name>"), in the same transaction as the change itself.
"""
import phones


def international_phone_numbers(cursor):
    """Phone numbers saved before other Central African countries were added (9
    Cameroon digits, or older ones exactly as typed) get their international form,
    +237..., like every new number. A number that can't be read, or whose new form
    another account already has, stays as it is; logging in still finds it."""
    cursor.execute("SELECT id, phoneNumber, guardianPhone FROM users ORDER BY id")
    users = [dict(row) for row in cursor.fetchall()]
    taken = {user["phoneNumber"] for user in users}
    for user in users:
        new = phones.stored_form(user["phoneNumber"])
        if new != user["phoneNumber"] and new not in taken:
            cursor.execute("UPDATE users SET phoneNumber = ? WHERE id = ?", (new, user["id"]))
            taken.add(new)
        if user["guardianPhone"]:
            guardian = phones.stored_form(user["guardianPhone"])
            if guardian != user["guardianPhone"]:
                cursor.execute("UPDATE users SET guardianPhone = ? WHERE id = ?", (guardian, user["id"]))


UPGRADES = [
    ("international-phone-numbers", international_phone_numbers),
]
