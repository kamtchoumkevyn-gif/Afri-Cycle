"""Directions to the buyer, unread messages, and phone notifications (Web Push)."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import directions
import webpush
from helpers import auth_header, new_buyer_with_profile, new_category, new_user
from models.app_setting import get_setting
from models.push_subscription import get_subscriptions_for_user

DOUALA = [4.0511, 9.7679]
BUYER_AT = [4.0611, 9.7579]


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
    directions._cache.clear()
    monkeypatch.setattr(directions, "MIN_SECONDS_BETWEEN_REQUESTS", 0)
    monkeypatch.setattr(directions, "_last_request_at", 0.0)
    monkeypatch.setattr(directions, "TURN_FILE", str(tmp_path / "routing-turn"))
    monkeypatch.setattr(webpush, "RUN_IN_BACKGROUND", False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)


# ---- A routing server answer, shaped like routing.openstreetmap.de's ----

def osrm_answer(start=DOUALA, end=BUYER_AT):
    corner = [end[0], start[1]]
    def step(kind, at, name="", modifier=None, distance=0.0, duration=0.0, **extra):
        maneuver = {"type": kind, "location": [at[1], at[0]], "bearing_before": 0, "bearing_after": 0}
        if modifier:
            maneuver["modifier"] = modifier
        maneuver.update(extra)
        return {"maneuver": maneuver, "name": name, "mode": "walking", "distance": distance, "duration": duration,
                "geometry": {"type": "LineString", "coordinates": [[at[1], at[0]]]}, "intersections": [],
                "driving_side": "right", "weight": duration}
    return {
        "code": "Ok",
        "routes": [{
            "distance": 1574.3, "duration": 1133.5, "weight": 1133.5, "weight_name": "duration",
            "geometry": {"type": "LineString", "coordinates": [[start[1], start[0]], [corner[1], corner[0]], [end[1], end[0]]]},
            "legs": [{"distance": 1574.3, "duration": 1133.5, "summary": "Rue Joss", "weight": 1133.5, "steps": [
                step("depart", start, "Boulevard de la Liberté", distance=1112.0, duration=800.6),
                step("turn", corner, "Rue Joss", "left", 462.3, 332.9),
                step("arrive", end, "Rue Joss", "right"),
            ]}],
        }],
        "waypoints": [{"location": [start[1], start[0]], "name": "Boulevard de la Liberté", "hint": "x"},
                      {"location": [end[1], end[0]], "name": "Rue Joss", "hint": "y"}],
    }


def login_seller():
    seller = new_user("677000001", "seller", "Jean")
    return seller, auth_header(seller, "seller")


# ---- Directions ----

@pytest.mark.parametrize("maneuver, name, expected", [
    ({"type": "depart", "bearing_after": 0}, "Rue Joss", "Head north on Rue Joss"),
    ({"type": "depart", "bearing_after": 128}, "", "Head south-east"),
    ({"type": "turn", "modifier": "left"}, "Rue Joss", "Turn left onto Rue Joss"),
    ({"type": "turn", "modifier": "slight right"}, "", "Bear right"),
    ({"type": "turn", "modifier": "sharp left"}, "Avenue Kennedy", "Turn sharp left onto Avenue Kennedy"),
    ({"type": "new name", "modifier": "straight"}, "Rue de la Joie", "Continue on Rue de la Joie"),
    ({"type": "continue", "modifier": "straight"}, "", "Continue straight on"),
    ({"type": "roundabout", "modifier": "right", "exit": 2}, "Avenue Ahidjo", "At the roundabout, take exit 2 onto Avenue Ahidjo"),
    ({"type": "rotary", "modifier": "right", "exit": 12}, "", "At the roundabout, take exit 12"),
    ({"type": "fork", "modifier": "slight left"}, "", "Keep left"),
    ({"type": "end of road", "modifier": "right"}, "Rue Njo-Njo", "At the end of the road, turn right onto Rue Njo-Njo"),
    ({"type": "turn", "modifier": "uturn"}, "", "Make a U-turn"),
    ({"type": "arrive", "modifier": "left"}, "Rue Joss", "You have arrived"),
])
def test_instructions_read_like_plain_english(maneuver, name, expected):
    assert directions.instruction({"maneuver": maneuver, "name": name}) == expected


def test_directions_give_the_road_route_with_steps(client, monkeypatch):
    calls = []
    monkeypatch.setattr(directions, "fetch_json", lambda url, referer=None: calls.append(url) or osrm_answer())
    _, headers = login_seller()
    response = client.get("/directions?from=4.0511,9.7679&to=4.0611,9.7579&mode=foot", headers=headers)
    assert response.status_code == 200
    route = response.get_json()
    assert route["distance"] == 1574 and route["duration"] == 1134 and route["mode"] == "foot"
    assert route["line"][0] == DOUALA and route["line"][-1] == BUYER_AT  # [lat, lng], like Leaflet
    assert [s["text"] for s in route["steps"]] == [
        "Head north on Boulevard de la Liberté", "Turn left onto Rue Joss", "You have arrived"]
    assert route["steps"][1]["at"] == [BUYER_AT[0], DOUALA[1]]
    assert "OpenStreetMap" in route["credit"]
    # The routing server wants longitude first, and one profile per way of travel
    assert calls == ["https://routing.openstreetmap.de/routed-foot/route/v1/driving/"
                     "9.767900,4.051100;9.757900,4.061100?overview=full&geometries=geojson&steps=true"]


def test_motorbikes_get_car_roads(client, monkeypatch):
    calls = []
    monkeypatch.setattr(directions, "fetch_json", lambda url, referer=None: calls.append(url) or osrm_answer())
    _, headers = login_seller()
    assert client.get("/directions?from=4.0511,9.7679&to=4.0611,9.7579&mode=car", headers=headers).status_code == 200
    assert "/routed-car/" in calls[0]


def test_same_trip_is_asked_once_then_remembered(client, monkeypatch):
    calls = []
    monkeypatch.setattr(directions, "fetch_json", lambda url, referer=None: calls.append(url) or osrm_answer())
    _, headers = login_seller()
    for _ in range(3):
        assert client.get("/directions?from=4.0511,9.7679&to=4.0611,9.7579", headers=headers).status_code == 200
    assert len(calls) == 1


def test_requests_to_the_routing_server_are_a_second_apart(monkeypatch):
    monkeypatch.setattr(directions, "MIN_SECONDS_BETWEEN_REQUESTS", 1.0)
    monkeypatch.setattr(directions, "fetch_json", lambda url, referer=None: osrm_answer())
    waits = []
    monkeypatch.setattr(directions.time, "sleep", waits.append)
    directions.get_route(DOUALA, BUYER_AT)
    directions.get_route(DOUALA, [4.07, 9.76])  # a different trip, straight after
    assert waits and 0.9 < waits[-1] <= 1.0


@pytest.mark.skipif(directions.fcntl is None, reason="needs file locks (Linux, macOS)")
def test_server_processes_share_the_one_request_a_second_rule(monkeypatch):
    # Another server process (gunicorn worker) asked the routing server a moment ago
    with open(directions.TURN_FILE, "w") as other:
        other.write(repr(time.time()))
    monkeypatch.setattr(directions, "MIN_SECONDS_BETWEEN_REQUESTS", 1.0)
    monkeypatch.setattr(directions, "fetch_json", lambda url, referer=None: osrm_answer())
    waits = []
    monkeypatch.setattr(directions.time, "sleep", waits.append)
    directions.get_route(DOUALA, BUYER_AT)
    assert waits and 0.9 < waits[0] <= 1.0
    with open(directions.TURN_FILE) as turn:  # and this process's request is noted for the others
        assert time.time() - float(turn.read()) < 5

    # A time in the future (the clock was moved back) costs one normal wait, not hours
    with open(directions.TURN_FILE, "w") as other:
        other.write(repr(time.time() + 3600))
    directions.get_route(DOUALA, [4.07, 9.76])
    assert waits[-1] == 1.0


@pytest.mark.skipif(directions.fcntl is None, reason="needs file locks (Linux, macOS)")
def test_waiting_for_a_busy_routing_turn_gives_up_in_time(client, monkeypatch):
    monkeypatch.setattr(directions, "QUEUE_SECONDS", 0.3)
    monkeypatch.setattr(directions, "fetch_json", lambda url, referer=None: osrm_answer())
    _, headers = login_seller()
    with open(directions.TURN_FILE, "a+") as other:
        directions.fcntl.flock(other, directions.fcntl.LOCK_EX)  # another process is asking
        started = time.time()
        response = client.get("/directions?from=4.0511,9.7679&to=4.0611,9.7579", headers=headers)
        assert response.status_code == 502 and 0.3 <= time.time() - started < 3
    # Once the other process is done, it's this one's turn
    assert client.get("/directions?from=4.0511,9.7679&to=4.0611,9.7579", headers=headers).status_code == 200


def test_routing_server_sees_who_is_asking(monkeypatch):
    seen = {}

    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(osrm_answer()).encode()

    def fake_urlopen(request, timeout):
        seen.update(dict(request.header_items()), timeout=timeout)
        return Answer()
    monkeypatch.setattr(directions.urllib.request, "urlopen", fake_urlopen)
    directions.get_route(DOUALA, BUYER_AT, referer="https://afri-cycle.onrender.com/")
    assert seen["User-agent"].startswith("Africycle/")
    assert seen["Referer"] == "https://afri-cycle.onrender.com/"
    assert seen["timeout"] <= 15


def test_directions_need_a_login_and_sensible_points(client, monkeypatch):
    monkeypatch.setattr(directions, "fetch_json", lambda url, referer=None: osrm_answer())
    assert client.get("/directions?from=4.05,9.76&to=4.06,9.75").status_code == 401
    _, headers = login_seller()
    for query in ("from=4.05&to=4.06,9.75", "from=91,9.7&to=4.06,9.75", "from=abc,def&to=4.06,9.75",
                  "from=4.05,9.76&to=4.06,9.75&mode=plane", "from=NaN,9.76&to=4.06,9.75",
                  "from=4.05,9.76&to=9.30,13.40&mode=car"):  # Douala to Garoua: too far
        assert client.get(f"/directions?{query}", headers=headers).status_code == 400, query


def test_no_route_and_server_trouble_are_explained(client, monkeypatch):
    _, headers = login_seller()
    monkeypatch.setattr(directions, "fetch_json", lambda url, referer=None: {"code": "NoRoute", "message": "Impossible route"})
    response = client.get("/directions?from=4.0511,9.7679&to=4.0611,9.7579", headers=headers)
    assert response.status_code == 404 and "No road route" in response.get_json()["message"]

    def down(url, referer=None):
        raise directions.RoutingUnavailable("timed out")
    monkeypatch.setattr(directions, "fetch_json", down)
    response = client.get("/directions?from=4.0511,9.7679&to=4.0611,9.7580", headers=headers)
    assert response.status_code == 502 and "aren't available" in response.get_json()["message"]

    monkeypatch.setattr(directions, "fetch_json", lambda url, referer=None: {"code": "Ok", "routes": [{"oops": 1}]})
    assert client.get("/directions?from=4.0511,9.7679&to=4.0611,9.7581", headers=headers).status_code == 502


def test_deliveries_say_where_the_buyer_is(client):
    seller, headers = login_seller()
    category = new_category()
    buyer = new_buyer_with_profile("677000002", BUYER_AT[0], BUYER_AT[1], 200, category)
    client.post("/seller/notify-buyer", json={"buyerId": buyer, "materialCategoryId": category, "onTheWay": True},
                headers=headers)
    trip = client.get("/notifications", headers=headers).get_json()["notifications"][0]
    assert [trip["buyerLatitude"], trip["buyerLongitude"]] == BUYER_AT


# ---- Unread messages ----

def test_unread_messages_are_counted_until_the_conversation_is_opened(client):
    jean = new_user("677000001", "seller", "Jean")
    marie = new_user("677000002", "buyer", "Marie")
    paul = new_user("677000003", "buyer", "Paul")
    for sender, text in ((marie, "Bonjour"), (marie, "Are you coming?"), (paul, "I pay 260 FCFA")):
        assert client.post("/chat/send", json={"receiverId": jean, "messageText": text},
                           headers=auth_header(sender, "buyer")).status_code == 201

    summary = client.get("/chat/unread", headers=auth_header(jean, "seller")).get_json()
    assert summary["unread"] == 3
    assert summary["bySender"] == {str(marie): 2, str(paul): 1}
    assert summary["latest"]["senderName"] == "Paul" and summary["latest"]["messageText"] == "I pay 260 FCFA"

    conversations = client.get("/chat/conversations", headers=auth_header(jean, "seller")).get_json()["conversations"]
    assert {c["otherUserName"]: c["unread"] for c in conversations} == {"Marie": 2, "Paul": 1}

    # Looking at the page in the background doesn't count as reading
    client.get(f"/chat/messages/{marie}?read=0", headers=auth_header(jean, "seller"))
    assert client.get("/chat/unread", headers=auth_header(jean, "seller")).get_json()["unread"] == 3
    client.get(f"/chat/messages/{marie}", headers=auth_header(jean, "seller"))
    summary = client.get("/chat/unread", headers=auth_header(jean, "seller")).get_json()
    assert summary["unread"] == 1 and summary["bySender"] == {str(paul): 1}

    # Replying also means Jean has read Paul's message; Paul hasn't read the reply yet
    client.post("/chat/send", json={"receiverId": paul, "messageText": "OK, 30 minutes"}, headers=auth_header(jean, "seller"))
    assert client.get("/chat/unread", headers=auth_header(jean, "seller")).get_json()["unread"] == 0
    assert client.get("/chat/unread", headers=auth_header(paul, "buyer")).get_json()["unread"] == 1
    assert client.get("/chat/unread").status_code == 401


# ---- Push encryption, checked against the published example ----

def test_encryption_matches_rfc_8291_example():
    sender = ec.derive_private_key(int.from_bytes(webpush.from_b64url("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"),
                                   ec.SECP256R1())
    body = webpush.encrypt(
        b"When I grow up, I want to be a watermelon",
        "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
        "BTBZMqHH6r4Tts7J_aSIgg",
        salt=webpush.from_b64url("DGv6ra1nlYgDCS1FRnbzlw"),
        sender_key=sender,
    )
    assert webpush.b64url(body) == (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml"
        "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT"
        "pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


class Device:
    """A browser's side of Web Push: its keys, and how it decrypts what arrives."""

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.public = self.key.public_key().public_bytes(serialization.Encoding.X962,
                                                         serialization.PublicFormat.UncompressedPoint)
        self.auth = b"0123456789abcdef"

    def keys(self):
        return {"p256dh": webpush.b64url(self.public), "auth": webpush.b64url(self.auth)}

    def decrypt(self, body):
        salt, record_size, id_length = body[:16], int.from_bytes(body[16:20], "big"), body[20]
        sender_public = body[21:21 + id_length]
        assert record_size == 4096
        sender = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), sender_public)
        secret = self.key.exchange(ec.ECDH(), sender)
        def hkdf(salt_value, ikm, info, length):
            return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt_value, info=info).derive(ikm)
        ikm = hkdf(self.auth, secret, b"WebPush: info\x00" + self.public + sender_public, 32)
        plain = AESGCM(hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)).decrypt(
            hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12), body[21 + id_length:], None)
        assert plain.rstrip(b"\x00").endswith(b"\x02")
        return json.loads(plain.rstrip(b"\x00")[:-1])


def test_each_message_is_encrypted_differently_but_readable_by_the_device():
    device = Device()
    first = webpush.encrypt(b'{"title": "Hi"}', **{"p256dh": device.keys()["p256dh"], "auth_secret": device.keys()["auth"]})
    second = webpush.encrypt(b'{"title": "Hi"}', device.keys()["p256dh"], device.keys()["auth"])
    assert first != second
    assert device.decrypt(first) == device.decrypt(second) == {"title": "Hi"}


def test_vapid_header_is_signed_by_the_apps_key():
    key = webpush.vapid_private_key()
    header = webpush.vapid_authorization("https://fcm.googleapis.com/fcm/send/abc", "https://afri-cycle.onrender.com", key)
    token = header.split("t=")[1].split(",")[0]
    public = header.split("k=")[1]
    assert public == webpush.application_server_key()
    claims = jwt.decode(token, key.public_key(), algorithms=["ES256"], audience="https://fcm.googleapis.com")
    assert claims["sub"] == "https://afri-cycle.onrender.com"
    assert 0 < claims["exp"] - time.time() <= 24 * 3600  # push services refuse longer


def test_app_key_is_made_once_and_kept(client, monkeypatch):
    first = webpush.application_server_key()
    assert len(webpush.from_b64url(first)) == 65
    assert webpush.application_server_key() == first
    assert get_setting("vapid_private_key")
    other = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setenv("VAPID_PRIVATE_KEY", webpush.b64url(other.private_numbers().private_value.to_bytes(32, "big")))
    assert webpush.application_server_key() == webpush.b64url(webpush.public_key_bytes(other))
    user = new_user("677000001", "seller")
    assert client.get("/push/key").status_code == 401
    assert client.get("/push/key", headers=auth_header(user, "seller")).get_json()["publicKey"] == webpush.application_server_key()


# ---- Turning notifications on and off ----

FCM = "https://fcm.googleapis.com/fcm/send/device-123"


def test_devices_sign_up_and_move_between_accounts(client):
    jean = new_user("677000001", "seller", "Jean")
    marie = new_user("677000002", "buyer", "Marie")
    device = Device()
    assert client.post("/push/subscribe", json={"endpoint": FCM, "keys": device.keys()}).status_code == 401
    assert client.post("/push/subscribe", json={"endpoint": FCM, "keys": device.keys()},
                       headers=auth_header(jean, "seller")).status_code == 201
    assert [s["endpoint"] for s in get_subscriptions_for_user(jean)] == [FCM]
    # Same phone, Marie logs in and turns notifications on: it's now hers only
    client.post("/push/subscribe", json={"endpoint": FCM, "keys": device.keys()}, headers=auth_header(marie, "buyer"))
    assert get_subscriptions_for_user(jean) == [] and len(get_subscriptions_for_user(marie)) == 1
    # Jean can't switch off Marie's device; Marie can
    client.delete("/push/subscribe", json={"endpoint": FCM}, headers=auth_header(jean, "seller"))
    assert len(get_subscriptions_for_user(marie)) == 1
    assert client.delete("/push/subscribe", json={"endpoint": FCM}, headers=auth_header(marie, "buyer")).status_code == 200
    assert get_subscriptions_for_user(marie) == []


def test_only_real_push_services_and_proper_keys_are_accepted(client):
    jean = new_user("677000001", "seller", "Jean")
    headers = auth_header(jean, "seller")
    keys = Device().keys()
    for endpoint in ("http://169.254.169.254/latest/meta-data", "https://evil.example/fcm.googleapis.com",
                     "http://fcm.googleapis.com/fcm/send/x", "ftp://push.apple.com/x", None, 42, "https://" + "a" * 1200):
        assert client.post("/push/subscribe", json={"endpoint": endpoint, "keys": keys}, headers=headers).status_code == 400, endpoint
    for ok in ("https://updates.push.services.mozilla.com/wpush/v2/abc", "https://web.push.apple.com/QOx",
               "https://wns2-par02p.notify.windows.com/w/?token=abc"):
        assert client.post("/push/subscribe", json={"endpoint": ok, "keys": keys}, headers=headers).status_code == 201, ok
    for bad_keys in ({"p256dh": keys["p256dh"]}, {"p256dh": "short", "auth": keys["auth"]},
                     {"p256dh": keys["auth"], "auth": keys["auth"]}, {"p256dh": keys["p256dh"], "auth": "!!!"}, "nope"):
        assert client.post("/push/subscribe", json={"endpoint": FCM, "keys": bad_keys}, headers=headers).status_code == 400


# ---- Sending ----

class FakePushService:
    """Plays a browser's push service on this machine, recording what the app posts."""

    def __init__(self, answer=201):
        received = self.received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                headers = {name.lower(): value for name, value in self.headers.items()}
                received.append({"path": self.path, "headers": headers, "body": body})
                self.send_response(answer)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def push_service(monkeypatch):
    services = []

    def start(answer=201):
        service = FakePushService(answer)
        monkeypatch.setenv("PUSH_TEST_ENDPOINT_PREFIX", service.base + "/")
        services.append(service)
        return service
    yield start
    for service in services:
        service.close()


def test_new_message_reaches_the_receivers_phone(client, push_service):
    service = push_service()
    jean = new_user("677000001", "seller", "Jean Mbarga")
    marie = new_user("677000002", "buyer", "Marie")
    phone = Device()
    client.post("/push/subscribe", json={"endpoint": service.base + "/push/marie-phone", "keys": phone.keys()},
                headers=auth_header(marie, "buyer"))

    text = "I'm at the market gate with 40 kg of scrap iron. " * 5
    client.post("/chat/send", json={"receiverId": marie, "messageText": text}, headers=auth_header(jean, "seller"))

    assert len(service.received) == 1
    delivery = service.received[0]
    assert delivery["path"] == "/push/marie-phone"
    assert delivery["headers"]["content-encoding"] == "aes128gcm"
    assert int(delivery["headers"]["ttl"]) > 0 and delivery["headers"]["urgency"] == "high"
    assert delivery["headers"]["topic"] == f"chat-{jean}"
    token = delivery["headers"]["authorization"].split("t=")[1].split(",")[0]
    claims = jwt.decode(token, webpush.vapid_private_key().public_key(), algorithms=["ES256"], audience=service.base)
    assert claims["sub"].startswith("http")
    message = phone.decrypt(delivery["body"])
    assert message["title"] == "Message from Jean Mbarga"
    assert message["body"].startswith("I'm at the market gate") and len(message["body"]) <= 120
    assert message["url"] == f"/chat.html?with={jean}" and message["tag"] == f"chat-{jean}"
    # Jean has no device signed up, and isn't notified of his own message
    assert all(r["path"] == "/push/marie-phone" for r in service.received)


def test_device_that_turned_notifications_off_is_forgotten(client, push_service):
    service = push_service(answer=410)
    jean = new_user("677000001", "seller", "Jean")
    marie = new_user("677000002", "buyer", "Marie")
    client.post("/push/subscribe", json={"endpoint": service.base + "/push/old-phone", "keys": Device().keys()},
                headers=auth_header(marie, "buyer"))
    client.post("/chat/send", json={"receiverId": marie, "messageText": "Hello"}, headers=auth_header(jean, "seller"))
    assert len(service.received) == 1
    assert get_subscriptions_for_user(marie) == []


def test_unreachable_push_service_doesnt_break_sending(client, monkeypatch):
    monkeypatch.setenv("PUSH_TEST_ENDPOINT_PREFIX", "http://127.0.0.1:9/")  # nothing listens there
    jean = new_user("677000001", "seller", "Jean")
    marie = new_user("677000002", "buyer", "Marie")
    client.post("/push/subscribe", json={"endpoint": "http://127.0.0.1:9/push/x", "keys": Device().keys()},
                headers=auth_header(marie, "buyer"))
    response = client.post("/chat/send", json={"receiverId": marie, "messageText": "Hello"}, headers=auth_header(jean, "seller"))
    assert response.status_code == 201
    assert len(get_subscriptions_for_user(marie)) == 1  # kept: maybe just a network hiccup


def test_buyer_is_told_when_a_seller_is_coming_on_the_way_and_arrived(client, push_service):
    service = push_service()
    seller, headers = login_seller()
    category = new_category("Scrap Iron")
    buyer = new_buyer_with_profile("677000002", BUYER_AT[0], BUYER_AT[1], 200, category, name="Marie")
    phone = Device()
    client.post("/push/subscribe", json={"endpoint": service.base + "/push/marie", "keys": phone.keys()},
                headers=auth_header(buyer, "buyer"))

    trip = client.post("/seller/notify-buyer", json={"buyerId": buyer, "materialCategoryId": category},
                       headers=headers).get_json()["notificationId"]
    client.patch(f"/notifications/{trip}/status", json={"status": "in transit"}, headers=headers)
    client.patch(f"/notifications/{trip}/status", json={"status": "arrived"}, headers=headers)
    client.patch(f"/notifications/{trip}/status", json={"status": "completed"}, headers=auth_header(buyer, "buyer"))

    messages = [phone.decrypt(r["body"]) for r in service.received]
    assert [m["title"] for m in messages] == ["Jean is coming to you", "Jean is on the way", "Jean has arrived"]
    assert messages[0]["body"] == "Material: Scrap Iron. Open Africycle to see the details."
    assert all(m["url"] == "/buyer-dashboard.html" and m["tag"] == f"trip-{trip}" for m in messages)


def test_tapping_a_photo_sends_on_the_way_straight_away(client, push_service):
    service = push_service()
    seller, headers = login_seller()
    category = new_category("Plastic")
    buyer = new_buyer_with_profile("677000002", BUYER_AT[0], BUYER_AT[1], 200, category, name="Marie")
    phone = Device()
    client.post("/push/subscribe", json={"endpoint": service.base + "/push/marie", "keys": phone.keys()},
                headers=auth_header(buyer, "buyer"))
    client.post("/seller/notify-buyer", json={"buyerId": buyer, "materialCategoryId": category, "onTheWay": True},
                headers=headers)
    assert [phone.decrypt(r["body"])["title"] for r in service.received] == ["Jean is on the way"]
