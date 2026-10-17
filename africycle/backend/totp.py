"""Two-step login for admins: the 6-digit codes of authenticator apps (RFC 6238).

Google Authenticator, Microsoft Authenticator and similar apps all make the same
codes from a shared secret and the time: a new code every 30 seconds. The secret is
kept encrypted in the database with a key made from JWT_SECRET_KEY, so a copy of the
database alone can't produce codes. Changing JWT_SECRET_KEY therefore turns every
admin's two-step login off (see the README for how to set it up again).
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken

from config import Config

STEP_SECONDS = 30
DIGITS = 6
ISSUER = "Africycle"


def _box():
    key = hashlib.sha256(("africycle-totp:" + Config.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def new_secret():
    """A random secret, as the base32 text people type into an authenticator app."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def seal(secret):
    return _box().encrypt(secret.encode("ascii")).decode("ascii")


def unseal(sealed):
    """The secret, or None if it can't be read (JWT_SECRET_KEY changed)."""
    try:
        return _box().decrypt(sealed.encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError, AttributeError):
        return None


def code_at(secret, step):
    key = base64.b32decode(secret)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10 ** DIGITS).zfill(DIGITS)


def current_step(now=None):
    return int((time.time() if now is None else now) // STEP_SECONDS)


def check(secret, code, last_step=None, now=None):
    """The time step the code belongs to if it's right, else None.

    Accepts the code before and after the current one (a phone clock a little off),
    but never a step already used (last_step), so an overheard code can't be replayed."""
    code = "".join(str(code or "").split())
    if not secret or len(code) != DIGITS or not code.isdigit():
        return None
    step = current_step(now)
    for candidate in (step - 1, step, step + 1):
        if last_step is not None and candidate <= last_step:
            continue
        if hmac.compare_digest(code_at(secret, candidate), code):
            return candidate
    return None


def setup_link(secret, account):
    """The otpauth:// link that opens an authenticator app with the account filled in."""
    label = quote(f"{ISSUER}:{account}", safe=":")
    return f"otpauth://totp/{label}?secret={secret}&issuer={ISSUER}&digits={DIGITS}&period={STEP_SECONDS}"
