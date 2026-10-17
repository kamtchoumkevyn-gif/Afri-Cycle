"""The voice guide's recordings.

Anyone may list and play them (the guide also helps on the login pages); only admins
record, replace and delete them, from the studio on the admin page.
"""
import base64
import binascii
import re

from flask import Blueprint, Response, jsonify, request

import i18n
from i18n import _
from models.guide_recording import (counts_by_language, delete_recording, get_recording, list_recordings,
                                    save_recording)
from auth_utils import client_ip
from models.admin_action import log_action
from routes.admin_routes import admin_or_error

guide_bp = Blueprint("guide_bp", __name__)

MAX_AUDIO_BYTES = 600_000  # about 30 seconds even in the biggest format phones record
MAX_TEXT_LENGTH = 1000
# What MediaRecorder records: WebM or Ogg (Opus) on Android and computers, MP4 on iPhones
AUDIO_DATA_URL = re.compile(
    r"data:(audio/(?:webm|ogg|mp4|x-m4a|mpeg|aac|wav|x-wav))((?:;[\w.+-]+=[\w.,+\"-]+)*);base64,([A-Za-z0-9+/=\s]+)")
SAME_AS = {"audio/x-m4a": "audio/mp4", "audio/x-wav": "audio/wav"}


def _looks_like(mime_type, raw):
    if len(raw) < 12:
        return False
    return {
        "audio/webm": raw[:4] == b"\x1a\x45\xdf\xa3",
        "audio/ogg": raw[:4] == b"OggS",
        "audio/mp4": raw[4:8] == b"ftyp",
        "audio/mpeg": raw[:3] == b"ID3" or (raw[0] == 0xFF and raw[1] & 0xE0 == 0xE0),
        "audio/aac": raw[0] == 0xFF and raw[1] & 0xF6 == 0xF0,
        "audio/wav": raw[:4] == b"RIFF" and raw[8:12] == b"WAVE",
    }[mime_type]


def decode_audio(data_url):
    """(mime_type, raw_bytes) for a real recording, else (None, error message)."""
    match = AUDIO_DATA_URL.fullmatch(data_url) if isinstance(data_url, str) else None
    problem = _("The recording is damaged or too long. Record it again.")
    if not match:
        return None, problem
    mime_type = SAME_AS.get(match.group(1), match.group(1))
    try:
        raw = base64.b64decode(re.sub(r"\s", "", match.group(3)), validate=True)
    except (binascii.Error, ValueError):
        return None, problem
    if len(raw) > MAX_AUDIO_BYTES or not _looks_like(mime_type, raw):
        return None, problem
    return mime_type, raw


@guide_bp.route("/guide/recordings/<language>", methods=["GET"])
def recordings_for(language):
    """Which guide sentences have a recording in this language: [{id, text, mimeType}]."""
    if not i18n.supported(language):
        return jsonify({"message": "Unknown language"}), 404
    response = jsonify({"language": language, "recordings": list_recordings(language)})
    response.headers["Cache-Control"] = "no-cache"  # a quick 304 while nothing changed
    response.add_etag()
    return response.make_conditional(request)


@guide_bp.route("/guide/recorded-languages", methods=["GET"])
def recorded_languages():
    """How many sentences are recorded in each language (to offer them as voices)."""
    response = jsonify({"languages": counts_by_language()})
    response.headers["Cache-Control"] = "no-cache"
    response.add_etag()
    return response.make_conditional(request)


@guide_bp.route("/guide/audio/<int:recording_id>", methods=["GET"])
def recording_audio(recording_id):
    recording = get_recording(recording_id)
    if not recording:
        return jsonify({"message": _("Recording not found")}), 404
    response = Response(base64.b64decode(recording["audioData"]), mimetype=recording["mimeType"])
    # A new recording gets a new id, so this one never changes
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@guide_bp.route("/admin/guide-recordings", methods=["POST"])
def add_recording():
    payload, error = admin_or_error()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    language = data.get("language")
    text = data.get("text")
    if not isinstance(language, str) or not i18n.supported(language):
        return jsonify({"message": "language must be one of " + ", ".join(i18n.available())}), 400
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
        return jsonify({"message": f"text must be the guide sentence in English (up to {MAX_TEXT_LENGTH} characters)"}), 400
    mime_type, raw = decode_audio(data.get("audio"))
    if mime_type is None:
        return jsonify({"message": raw}), 400
    recording_id = save_recording(language, text.strip(), mime_type,
                                  base64.b64encode(raw).decode("ascii"), payload["userId"])
    log_action(payload["userId"], "recording_saved", details=f"{language}: {text.strip()[:200]}",
               ip_address=client_ip())
    return jsonify({"message": _("Recording saved"), "id": recording_id}), 201


@guide_bp.route("/admin/guide-recordings/<int:recording_id>", methods=["DELETE"])
def remove_recording(recording_id):
    payload, error = admin_or_error()
    if error:
        return error
    if not delete_recording(recording_id):
        return jsonify({"message": _("Recording not found")}), 404
    log_action(payload["userId"], "recording_deleted", details=f"recording {recording_id}",
               ip_address=client_ip())
    return jsonify({"message": _("Recording removed")}), 200
