"""Phone numbers from the 11 countries of Central Africa (ECCAS)."""
import os
import sys

import pytest

import phones
from database import db
from models.user import find_user_by_phone, hash_password

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import phone_list  # noqa: E402

# A mobile number per country, as people there write it, and how it is saved
AT_HOME = {
    "CM": ("6 71 23 45 67", "+237671234567"),
    "AO": ("923 123 456", "+244923123456"),
    "BI": ("79 56 12 34", "+25779561234"),
    "CF": ("70 01 23 45", "+23670012345"),
    "TD": ("63 01 23 45", "+23563012345"),
    "CG": ("06 123 4567", "+242061234567"),
    "CD": ("0991 234 567", "+243991234567"),
    "GQ": ("222 123 456", "+240222123456"),
    "GA": ("077 12 34 56", "+24177123456"),
    "RW": ("0720 123 456", "+250720123456"),
    "ST": ("981 2345", "+2399812345"),
}


def register(client, **fields):
    body = {"name": "Amina", "password": "password123", "role": "seller", **fields}
    return client.post("/register", json=body)


def login(client, phone, country=None):
    body = {"phoneNumber": phone, "password": "password123"}
    if country:
        body["country"] = country
    return client.post("/login", json=body)


def problem(phone, country="CM"):
    with pytest.raises(phones.PhoneError) as error:
        phones.normalize(phone, country)
    return str(error.value)


# ---- Reading numbers ----

def test_the_eleven_countries_of_central_africa():
    assert set(phones.COUNTRIES) == {"CM", "AO", "BI", "CF", "TD", "CG", "CD", "GQ", "GA", "RW", "ST"}
    assert set(AT_HOME) == set(phones.COUNTRIES)
    assert list(phones.COUNTRIES)[0] == "CM"  # first in the list, and chosen when none is sent


@pytest.mark.parametrize("country", list(AT_HOME))
def test_each_countrys_numbers_are_recognised(country):
    typed, saved = AT_HOME[country]
    assert phones.normalize(typed, country) == saved
    assert phones.normalize(saved, "CM") == saved  # with its country code, whatever was chosen
    assert phones.normalize("00" + saved[1:], country) == saved
    assert phones.example(country) == typed  # the pages' example is a real number


@pytest.mark.parametrize("typed, country, saved", [
    ("677 12 34 56", "CM", "+237677123456"),
    ("+237 6 77 12 34 56", "CM", "+237677123456"),
    ("237677123456", "CM", "+237677123456"),
    ("6-77-12-34-56", "CM", "+237677123456"),
    ("(677) 123 456", "CM", "+237677123456"),
    ("٦٧٧١٢٣٤٥٦", "CM", "+237677123456"),  # Arabic-Indic digits
    ("222 22 33 44", "CM", "+237222223344"),  # a landline
    ("991 234 567", "CD", "+243991234567"),   # DR Congo without its leading 0
    ("788 123 456", "RW", "+250788123456"),
    ("62 01 23 45", "TD", "+23562012345"),
    # Gabon added a digit in 2019; numbers typed the old way are saved the new way
    ("07 28 01 50", "GA", "+24177280150"),
    ("04 12 34 56", "GA", "+24174123456"),
    ("06 12 34 56", "GA", "+24166123456"),
    ("05 05 05 05", "GA", "+24165050505"),
    ("02 04 04 04", "GA", "+24162040404"),
    ("01 71 71 71", "GA", "+24111717171"),
    ("+241 07 28 01 50", "CM", "+24177280150"),
])
def test_numbers_are_read_the_way_people_type_them(typed, country, saved):
    assert phones.normalize(typed, country) == saved


def test_wrong_numbers_are_explained():
    assert problem("") == "Enter your phone number"
    for wrong in ("12345", "577000001", "600000099", "677 12 34 56 78"):
        assert problem(wrong) == "Check your phone number: Cameroon numbers look like 6 71 23 45 67.", wrong
    assert "Cameroon numbers look like" in problem("88 12 34 56")  # free-call numbers can't be called back
    assert "outside Central Africa" in problem("+234 803 123 4567")  # Nigeria
    assert "outside Central Africa" in problem("+33 6 12 34 56 78", "GA")  # France
    assert problem("6" * 41) == "Your phone number is too long"
    assert problem("677123456", "FR") == "Choose a country from the list"
    with pytest.raises(phones.PhoneError) as error:
        phones.normalize("", "CM", guardian=True)
    assert str(error.value) == "Enter your guardian's phone number"


def test_a_number_from_another_country_says_which_to_choose():
    assert problem("63 01 23 45") == ("Check your phone number: Cameroon numbers look like 6 71 23 45 67. "
                                      "If it's a number from Burundi / Chad, choose that country in the list.")
    assert "from Cameroon, choose" in problem("677 12 34 56", "GA")


# ---- Signing up and logging in ----

@pytest.mark.parametrize("country", list(AT_HOME))
def test_people_from_every_country_can_sign_up_and_log_in(client, country):
    typed, saved = AT_HOME[country]
    response = register(client, phoneNumber=typed, country=country)
    assert response.status_code == 201, response.get_json()
    assert find_user_by_phone(saved)["name"] == "Amina"
    assert login(client, typed, country).status_code == 200
    assert login(client, saved).status_code == 200  # with the country code, any country chosen
    token = login(client, saved).get_json()["token"]
    me = client.get("/me", headers={"Authorization": f"Bearer {token}"}).get_json()
    assert me["phoneNumber"] == saved


def test_cameroon_is_assumed_when_no_country_is_sent(client):
    assert register(client, phoneNumber="677 12 34 56").status_code == 201
    assert find_user_by_phone("+237677123456")
    assert login(client, "677123456").status_code == 200


def test_one_number_typed_two_ways_is_one_account(client):
    assert register(client, phoneNumber="077 12 34 56", country="GA").status_code == 201
    response = register(client, phoneNumber="+241 77 12 34 56", country="CM")
    assert response.status_code == 400 and "already exists" in response.get_json()["message"]
    assert login(client, "07 12 34 56", "GA").status_code == 200  # Gabon's old way


def test_logging_in_with_the_wrong_country_chosen_still_works(client):
    assert register(client, phoneNumber="63 01 23 45", country="TD").status_code == 201
    assert login(client, "63 01 23 45", "CM").status_code == 200
    assert login(client, "63 01 23 45", "XX").status_code == 200
    assert login(client, "63 01 23 46", "TD").status_code == 401


def test_signing_up_with_the_wrong_country_says_which_one(client):
    response = register(client, phoneNumber="63 01 23 45", country="CM")
    assert response.status_code == 400
    assert "Chad, choose that country" in response.get_json()["message"]
    assert register(client, phoneNumber="677123456", country="FR").status_code == 400


def test_a_guardian_can_live_in_another_country(client):
    # A child in Chad whose mother lives in Cameroon
    child = {"name": "Junior", "phoneNumber": "63 01 23 45", "country": "TD", "isMinor": True,
             "guardianName": "Mama", "guardianPhone": "699 12 34 56", "guardianRelation": "mother"}
    response = register(client, **child)  # the mother's number read as a Chad number
    assert response.status_code == 400
    assert response.get_json()["message"].startswith("Check your guardian's phone number: Chad numbers")
    assert register(client, **child, guardianCountry="CM").status_code == 201
    assert find_user_by_phone("+23563012345")["guardianPhone"] == "+237699123456"

    assert register(client, name="Mama", phoneNumber="+237 699 12 34 56", role="guardian").status_code == 201
    token = login(client, "699123456", "CM").get_json()["token"]
    pending = client.get("/guardian/children", headers={"Authorization": f"Bearer {token}"}).get_json()["pending"]
    assert [kid["name"] for kid in pending] == ["Junior"]


def test_admin_numbers_may_be_written_without_country_code(client):
    # conftest sets ADMIN_PHONE_NUMBERS=699999999
    assert register(client, phoneNumber="+237 699 999 999", role="admin").status_code == 201
    assert register(client, phoneNumber="+241 77 99 99 99", country="GA", role="admin").status_code == 403


# ---- Accounts from before this update ----

def test_numbers_saved_before_other_countries_were_added_become_international(client):
    # The live database before this update: 9 Cameroon digits, also for a child's guardian
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (phoneNumber, passwordHash, name, role) VALUES (?, ?, ?, ?)",
                   ("699123456", hash_password("password123"), "Mama", "guardian"))
    cursor.execute("""INSERT INTO users (phoneNumber, passwordHash, name, role, isMinor, guardianName,
                                         guardianPhone, guardianRelation, guardianStatus)
                      VALUES (?, ?, 'Junior', 'seller', 1, 'Mama', ?, 'mother', 'pending')""",
                   ("671234567", hash_password("password123"), "699123456"))
    cursor.execute("DELETE FROM app_settings WHERE name = 'upgrade:international-phone-numbers'")
    conn.commit()
    conn.close()

    db.init_db()  # what the app does when it starts after the update
    assert find_user_by_phone("+237699123456")["name"] == "Mama"
    assert find_user_by_phone("+237671234567")["guardianPhone"] == "+237699123456"
    db.init_db()  # and again at the next start: nothing more to do
    assert find_user_by_phone("+237671234567")["guardianPhone"] == "+237699123456"

    # Same logins as before, and the guardian still finds the child
    token = login(client, "699 12 34 56").get_json()["token"]
    pending = client.get("/guardian/children", headers={"Authorization": f"Bearer {token}"}).get_json()["pending"]
    assert [kid["name"] for kid in pending] == ["Junior"]
    assert login(client, "+237671234567").status_code == 200


# ---- The pages' list ----

def test_the_pages_list_matches_the_server(client):
    assert phone_list.listed_in_page() == phone_list.country_list(), \
        "frontend/js/phone.js is out of date: run python tools/phone_list.py in backend/"
