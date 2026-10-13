"""Phone and computer notifications (Web Push), with no outside account or service.

When someone allows notifications, their browser gives the app an address at its push
service (Google's for Chrome and Samsung Internet, Mozilla's for Firefox, Apple's for
iPhones, Microsoft's for Edge) plus two keys. To notify that device, the app encrypts a
short message with those keys (RFC 8291) and posts it to that address, signed with the
app's own key (VAPID, RFC 8292). The device shows it even when Africycle isn't open.

The app's key pair is made once and kept in the database (app_settings), so it survives
restarts and deploys. To use a key of your own instead, set VAPID_PRIVATE_KEY.
"""
import base64
import json
import logging
import os
import re
import struct
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from models.app_setting import get_or_create_setting
from models.push_subscription import delete_subscription, get_subscriptions_for_user

log = logging.getLogger(__name__)

RECORD_SIZE = 4096
TTL_SECONDS = 24 * 60 * 60  # a phone that's switched off still gets it if back on within a day
SEND_TIMEOUT_SECONDS = 10
RUN_IN_BACKGROUND = True  # tests turn this off to check the result straight away

# The app only ever posts to real push services, never to an address someone made up
# (that could point the server at private machines). Tests may add a local address.
PUSH_SERVICE_HOSTS = ("fcm.googleapis.com", "push.services.mozilla.com", "push.apple.com", "notify.windows.com")
TOPIC = re.compile(r"[A-Za-z0-9_-]{1,32}")


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def from_b64url(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def is_push_service(endpoint):
    if not isinstance(endpoint, str) or len(endpoint) > 1000:
        return False
    test_prefix = os.environ.get("PUSH_TEST_ENDPOINT_PREFIX")
    if test_prefix and endpoint.startswith(test_prefix):
        return True
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in PUSH_SERVICE_HOSTS)


# ---- The app's signing key (VAPID) ----

def _new_private_key():
    key = ec.generate_private_key(ec.SECP256R1())
    return b64url(key.private_numbers().private_value.to_bytes(32, "big"))


def vapid_private_key():
    stored = os.environ.get("VAPID_PRIVATE_KEY") or get_or_create_setting("vapid_private_key", _new_private_key)
    return ec.derive_private_key(int.from_bytes(from_b64url(stored), "big"), ec.SECP256R1())


def public_key_bytes(private_key):
    return private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def application_server_key():
    """The app's public key, which browsers need in order to sign up for notifications."""
    return b64url(public_key_bytes(vapid_private_key()))


def vapid_authorization(endpoint, subject, private_key):
    """The Authorization header that proves the notification comes from this app."""
    parts = urlsplit(endpoint)
    claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int(time.time()) + 12 * 60 * 60, "sub": subject}
    token = jwt.encode(claims, private_key, algorithm="ES256", headers={"typ": "JWT"})
    return f"vapid t={token}, k={b64url(public_key_bytes(private_key))}"


# ---- Encryption (only the device can read the message, not the push service) ----

def _hkdf(salt, secret, info, length):
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(secret)


def encrypt(payload, p256dh, auth_secret, salt=None, sender_key=None):
    """payload (bytes) encrypted for one device, in the aes128gcm format of RFC 8188 with
    the Web Push keys of RFC 8291. Only tests pass salt and sender_key."""
    receiver_public = from_b64url(p256dh)
    receiver = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), receiver_public)
    sender_key = sender_key or ec.generate_private_key(ec.SECP256R1())
    sender_public = public_key_bytes(sender_key)
    salt = salt or os.urandom(16)

    shared_secret = sender_key.exchange(ec.ECDH(), receiver)
    ikm = _hkdf(from_b64url(auth_secret), shared_secret, b"WebPush: info\x00" + receiver_public + sender_public, 32)
    content_key = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    ciphertext = AESGCM(content_key).encrypt(nonce, payload + b"\x02", None)  # \x02 marks the last record
    header = salt + struct.pack("!IB", RECORD_SIZE, len(sender_public)) + sender_public
    return header + ciphertext


# ---- Sending ----

def send(subscription, message, subject):
    """Delivers one notification. Returns the push service's HTTP status (201 means
    accepted), or 0 when it couldn't be reached. Never raises."""
    try:
        endpoint = subscription["endpoint"]
        body = encrypt(json.dumps(message).encode(), subscription["p256dh"], subscription["authSecret"])
        headers = {
            "Authorization": vapid_authorization(endpoint, subject, vapid_private_key()),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(TTL_SECONDS),
            "Urgency": "high",
        }
        if TOPIC.fullmatch(str(message.get("tag", ""))):
            headers["Topic"] = message["tag"]  # a newer one replaces an undelivered older one
        request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=SEND_TIMEOUT_SECONDS) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except Exception as error:  # network trouble, a bad key stored for the device...
        log.warning("Notification not sent: %s: %s", type(error).__name__, error)
        return 0


def notify_user(user_id, message, subject):
    """Sends message ({"title", "body", "url", "tag"}) to every device on which user_id
    turned notifications on. Runs in the background so the sender doesn't wait."""
    subscriptions = get_subscriptions_for_user(user_id)
    if not subscriptions:
        return

    def deliver():
        for subscription in subscriptions:
            status = send(subscription, message, subject)
            if status in (404, 410):  # notifications were turned off, or the app was removed
                delete_subscription(subscription["endpoint"])
            elif status not in (200, 201, 202):
                log.warning("Push service answered %s", status)

    if RUN_IN_BACKGROUND:
        threading.Thread(target=deliver, daemon=True).start()
    else:
        deliver()


def short(text, limit=120):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"
