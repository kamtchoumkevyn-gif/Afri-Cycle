"""Africycle in many languages: every translation file is complete and safe, the language
menus match the files, and the server answers, notifies and gives directions in the
language each person chose."""
import json
import os
import re
import sys

import pytest

import directions
import i18n
import webpush
from helpers import auth_header, new_category, new_user
from test_navigation_alerts import Device, FakePushService, osrm_answer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import i18n_strings  # noqa: E402

FRONTEND = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
TEXTS = i18n_strings.all_texts()
CODES = i18n_strings.catalog_codes()

# Sentences that tell people which button to tap name it exactly as the button reads (the
# voice guide's too: someone who can't read listens for the same words on the button)
BUTTONS_IN_SENTENCES = {
    'Buyer notified. The map below shows the way; tap "I\'m leaving now" when you set off.': ("I'm leaving now",),
    'You\'re at {name}\'s buying point. Tap "I\'ve arrived".': ("I've arrived",),
    '{name} is {distance} away by road, about {time} by motorbike or car. Tap "I\'m coming" to be guided there.': ("I'm coming",),
    '{name} is {distance} away by road, about {time} on foot. Tap "I\'m coming" to be guided there.': ("I'm coming",),
    'No conversations yet. Open one from a buyer or delivery with "Message".': ("Message",),
    "Notifications weren't allowed. Tap Turn on to try again.": ("Turn on",),
    "Choose a material and tap Find buyers.": ("Find buyers",),
    "{name} is {distance} away in a straight line. Tap Route for the way by road.": ("Route",),
    # The voice guide
    "Welcome to Africycle. It helps you sell your scrap, water or organic waste to the buyer who pays the best price near you. If you have an account, touch the green button, Log in. If you are new, touch Create an account.":
        ("Log in", "Create an account"),
    "Log in. Choose your country and type your phone number. Choose who you are: seller, buyer or parent. Type your password, then touch the green button, Log in.":
        ("Log in",),
    "Create your account. Type your name, choose your country and type your phone number. If you are under 18, tick the box and give your parent's details. Choose what you will do, type a password twice, then touch Create account.":
        ("Create account",),
    "Find a buyer. Choose the material you are carrying, then touch the green button, Find buyers. The buyers near you appear on the map and in the list, the best price first. Touch a buyer to see their prices.":
        ("Find buyers",),
    "Your trip to the buyer. The map shows the way. When you set off, touch I'm leaving now. When you get there, touch I've arrived. You can also call the buyer or send a message.":
        ("I'm leaving now", "I've arrived"),
    "Your sales: what buyers recorded buying from you. Touch Receipt to see the weight, the price, the total and the photos.":
        ("Receipt",),
    "Your prices. Choose a material, type your price for one kilo, then touch Save price. Then add a photo of the material: collectors touch it to tell you they are coming.":
        ("Save price",),
    "Collectors coming to you. The map shows where they are. When a collector has arrived and you have weighed the material, touch Record purchase.":
        ("Record purchase",),
    "Record a purchase. Choose the collector and the material. Type the weight in kilos and the price for one kilo. Touch Take a photo to add pictures of what you bought. Then touch Record purchase.":
        ("Take a photo", "Record purchase"),
    "Your purchases. Touch Receipt to see a receipt and its photos, or to add a photo.":
        ("Receipt",),
    "This is the receipt: who sold, what, how many kilos, the price per kilo and the total paid. Below are the photos of the material. Touch Take a photo to add one.":
        ("Take a photo",),
    "The conversation. The newest message is at the bottom. Write your message in the box, then touch Send.":
        ("Send",),
    "The voice guide studio. Choose a language. For each sentence, touch Record and say it in that language, then touch Stop, listen, and touch Save.":
        ("Record", "Stop", "Save"),
    "You are offline. Africycle needs the internet. Check your mobile data or Wi-Fi, then touch Try again.":
        ("Try again",),
    "To hear each button before you use it, turn on Hear before you tap.":
        ("Hear before you tap",),
    "Hear before you tap is on. Touch anything once to hear it. Touch a button a second time to use it.":
        ("Hear before you tap",),
    "Hear before you tap is off. Buttons work with one touch again.":
        ("Hear before you tap",),
    "There is no voice for this language on this phone yet. Choose a language you understand under Voice.":
        ("Voice",),
    "Recording... Touch Stop when you have finished.":
        ("Stop",),
}


@pytest.fixture(autouse=True)
def quiet_services(monkeypatch, tmp_path):
    directions._cache.clear()
    monkeypatch.setattr(directions, "MIN_SECONDS_BETWEEN_REQUESTS", 0)
    monkeypatch.setattr(directions, "TURN_FILE", str(tmp_path / "routing-turn"))
    monkeypatch.setattr(webpush, "RUN_IN_BACKGROUND", False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)


def read(path):
    with open(os.path.join(FRONTEND, path), encoding="utf-8") as f:
        return f.read()


# ---- The translation files ----

def test_there_are_texts_from_pages_scripts_and_server():
    assert "Log in with your phone number" in i18n_strings.page_texts()          # login.html
    assert "Choose a material first." in i18n_strings.script_texts()             # seller-dashboard.js
    assert "This browser is too old to run Africycle. Update it, or open Africycle in Chrome, " \
           "Firefox, Samsung Internet or Safari." in i18n_strings.script_texts()  # compat.js
    assert "Invalid phone number or password" in i18n_strings.server_texts()      # auth_routes.py
    assert "Turn left onto {road}" in i18n_strings.server_texts()                 # directions.py
    assert len(TEXTS) > 400


def test_about_twenty_languages_including_africas_common_ones():
    assert len(CODES) >= 20
    for code in ("fr", "ar", "pt", "es", "zh", "sw", "ha", "yo", "ig", "am", "zu", "so", "rw", "ln", "wes"):
        assert code in CODES


@pytest.mark.parametrize("code", CODES)
def test_every_text_is_translated_safely(code):
    found = i18n_strings.problems(code, TEXTS)
    assert {kind: items for kind, items in found.items() if items} == {}


@pytest.mark.parametrize("code", CODES)
def test_translations_are_plain_text(code):
    catalog = i18n_strings.load(code)
    assert all(isinstance(key, str) and isinstance(value, str) for key, value in catalog.items())
    for english, translated in catalog.items():
        assert translated == translated.strip(), english
        assert "\n" not in translated and "\t" not in translated, english


@pytest.mark.parametrize("code", CODES)
def test_sentences_name_the_buttons_exactly(code):
    catalog = i18n_strings.load(code)
    for sentence, buttons in BUTTONS_IN_SENTENCES.items():
        for button in buttons:
            assert catalog[button].lower() in catalog[sentence].lower(), (sentence, catalog[button])


def test_language_menus_offer_exactly_the_translated_languages():
    page_menu = re.findall(r'\{ code: "([\w-]+)", name: "[^"]+"', read("js/i18n.js"))
    old_browser_list = re.search(r"var LANGUAGES = \[([^\]]+)\]", read("js/compat.js")).group(1)
    old_browser_menu = re.findall(r'"([\w-]+)"', old_browser_list)
    assert page_menu[:2] == ["en", "fr"]  # Cameroon's official languages first
    assert sorted(page_menu) == sorted(old_browser_menu) == sorted(["en"] + CODES)
    assert len(set(page_menu)) == len(page_menu)


def test_arabic_reads_right_to_left():
    assert '{ code: "ar", name: "العربية", rtl: true }' in read("js/i18n.js")
    assert "RIGHT_TO_LEFT = { ar: true }" in read("js/compat.js")


def test_every_page_loads_the_translations_first_and_has_a_language_menu():
    for page in ("index.html", "login.html", "register.html", "seller-dashboard.html", "buyer-dashboard.html",
                 "chat.html", "admin-dashboard.html", "guardian-dashboard.html", "offline.html"):
        html = read(page)
        scripts = re.findall(r'<script src="([^"]+)"', html)
        assert scripts and scripts[0].endswith("js/i18n.js"), page
        assert html.index("i18n.js") < html.index("</head>"), page
        if page != "offline.html":
            assert "data-language-menu" in html, page


# ---- The server ----

def test_server_messages_come_in_the_language_asked_for(client):
    new_user("677000001", "seller", "Jean")
    wrong = {"phoneNumber": "677000001", "password": "wrong-password", "role": "seller"}
    for asked, code in (("fr", "fr"), ("fr-CM,fr;q=0.9,en;q=0.5", "fr"), ("sw", "sw"), ("wes", "wes"), ("ar", "ar")):
        response = client.post("/login", json=wrong, headers={"Accept-Language": asked})
        assert response.status_code == 401
        assert response.get_json()["message"] == i18n.catalog(code)["Invalid phone number or password"], asked
        assert "Accept-Language" in response.headers["Vary"]
    for asked in ("en", "xx", "", "de-DE"):
        response = client.post("/login", json=wrong, headers={"Accept-Language": asked} if asked else {})
        assert response.get_json()["message"] == "Invalid phone number or password", asked


def test_translating_on_the_server():
    assert i18n._("Message from {name}", "fr", name="Awa") == "Message de Awa"
    assert i18n._("Message from {name}", "en", name="Awa") == "Message from Awa"
    assert i18n._("Not a text Africycle shows", "fr") == "Not a text Africycle shows"
    assert i18n._("Message from {name}", "klingon", name="Awa") == "Message from Awa"
    assert i18n.supported("ha") == "ha" and i18n.supported("../en") is None and i18n.supported(None) is None


def test_material_names_stay_english_in_the_database_and_are_shown_translated(client):
    seller = new_user("677000001", "seller", "Jean")
    new_category("Scrap Iron")
    data = client.get("/material-categories", headers=dict(auth_header(seller, "seller"), **{"Accept-Language": "fr"}))
    assert [c["name"] for c in data.get_json()["categories"]] == ["Scrap Iron"]  # t(name) on the page
    assert i18n.catalog("fr")["Scrap Iron"] == "Ferraille"


def test_directions_come_in_the_language_of_the_person_asking(client, monkeypatch):
    calls = []
    monkeypatch.setattr(directions, "fetch_json", lambda url, referer=None: calls.append(url) or osrm_answer())
    seller = new_user("677000001", "seller", "Jean")
    url = "/directions?from=4.0511,9.7679&to=4.0611,9.7579&mode=foot"
    steps = {}
    for code in ("fr", "sw", "am", "en"):
        headers = dict(auth_header(seller, "seller"), **{"Accept-Language": code})
        route = client.get(url, headers=headers).get_json()
        steps[code] = [step["text"] for step in route["steps"]]
        assert route["credit"] == "Route: OSRM (FOSSGIS) · map data © OpenStreetMap contributors"  # the page translates it
    assert steps["en"] == ["Head north on Boulevard de la Liberté", "Turn left onto Rue Joss", "You have arrived"]
    for code in ("fr", "sw", "am"):
        catalog = i18n.catalog(code)
        assert steps[code] == [catalog["Head north on {road}"].replace("{road}", "Boulevard de la Liberté"),
                               catalog["Turn left onto {road}"].replace("{road}", "Rue Joss"),
                               catalog["You have arrived"]]
    assert len(calls) == 1  # one trip asked once, then told in every language from memory


@pytest.fixture
def push_service(monkeypatch):
    services = []

    def start():
        service = FakePushService()
        monkeypatch.setenv("PUSH_TEST_ENDPOINT_PREFIX", service.base + "/")
        services.append(service)
        return service
    yield start
    for service in services:
        service.close()


def test_each_phone_is_notified_in_the_language_chosen_on_it(client, push_service):
    service = push_service()
    jean = new_user("677000001", "seller", "Jean")
    marie = new_user("677000002", "buyer", "Marie")
    phones = {"fr": Device(), "sw": Device(), "ar": Device(), "en": Device()}
    marie_headers = auth_header(marie, "buyer")
    # The page says which language it shows; a page that doesn't is covered by its header
    client.post("/push/subscribe", json={"endpoint": service.base + "/push/fr", "keys": phones["fr"].keys(),
                                         "language": "fr"}, headers=marie_headers)
    client.post("/push/subscribe", json={"endpoint": service.base + "/push/sw", "keys": phones["sw"].keys(),
                                         "language": "sw"}, headers=marie_headers)
    client.post("/push/subscribe", json={"endpoint": service.base + "/push/ar", "keys": phones["ar"].keys()},
                headers=dict(marie_headers, **{"Accept-Language": "ar"}))
    client.post("/push/subscribe", json={"endpoint": service.base + "/push/en", "keys": phones["en"].keys(),
                                         "language": "not-a-language"}, headers=marie_headers)

    client.post("/chat/send", json={"receiverId": marie, "messageText": "Bonjour"}, headers=auth_header(jean, "seller"))

    titles = {r["path"].rsplit("/", 1)[1]: phones[r["path"].rsplit("/", 1)[1]].decrypt(r["body"])["title"]
              for r in service.received}
    assert titles == {"fr": "Message de Jean", "sw": i18n._("Message from {name}", "sw", name="Jean"),
                      "ar": i18n._("Message from {name}", "ar", name="Jean"), "en": "Message from Jean"}
    assert titles["sw"] != "Message from Jean" and titles["ar"] != "Message from Jean"


def test_service_worker_keeps_the_translations_for_offline_use():
    assert r"/^\/i18n\/[\w-]+\.json$/.test(path)" in read("sw.js")


def test_catalog_files_are_valid_utf8_json_without_byte_order_marks():
    for code in CODES:
        with open(os.path.join(FRONTEND, "i18n", f"{code}.json"), "rb") as f:
            raw = f.read()
        assert not raw.startswith(b"\xef\xbb\xbf"), code
        json.loads(raw.decode("utf-8"))
