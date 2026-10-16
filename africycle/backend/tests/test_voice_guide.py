"""The voice guide for people who can't read: its recordings on the server, and its
place on every page."""
import base64
import json
import os
import re

from app import CONTENT_SECURITY_POLICY, FRONTEND_DIR
from helpers import auth_header, new_user

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 60     # what Chrome and Android record
OGG = b"OggS" + b"\x00" * 60                   # Firefox
MP4 = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 60  # iPhone
SENTENCE = "Welcome to Africycle."


def audio_url(raw, mime="audio/webm;codecs=opus"):
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def save(client, user, language="ff", text=SENTENCE, audio=None, role="admin"):
    return client.post("/admin/guide-recordings", json={
        "language": language, "text": text, "audio": audio if audio is not None else audio_url(WEBM)
    }, headers=auth_header(user, role))


def read(path):
    with open(os.path.join(FRONTEND_DIR, path), encoding="utf-8") as f:
        return f.read()


# ---- Recordings on the server ----

def test_an_admin_records_a_sentence_and_everyone_can_play_it(client):
    admin = new_user("699999999", "admin", "Admin")
    saved = save(client, admin)
    assert saved.status_code == 201
    recording_id = saved.get_json()["id"]

    listed = client.get("/guide/recordings/ff")  # no login needed: the guide helps before logging in
    assert listed.status_code == 200
    assert listed.get_json()["recordings"] == [{"id": recording_id, "text": SENTENCE, "mimeType": "audio/webm"}]
    audio = client.get(f"/guide/audio/{recording_id}")
    assert audio.status_code == 200 and audio.mimetype == "audio/webm" and audio.data == WEBM
    assert "immutable" in audio.headers["Cache-Control"]
    assert client.get("/guide/recordings/sg").get_json()["recordings"] == []  # other languages untouched


def test_the_guide_knows_which_languages_have_recordings(client):
    admin = new_user("699999999", "admin", "Admin")
    assert client.get("/guide/recorded-languages").get_json()["languages"] == {}
    save(client, admin, language="ff")
    save(client, admin, language="ff", text="Another sentence.")
    save(client, admin, language="sg")
    assert client.get("/guide/recorded-languages").get_json()["languages"] == {"ff": 2, "sg": 1}


def test_recording_again_replaces_the_old_recording(client):
    admin = new_user("699999999", "admin", "Admin")
    first = save(client, admin).get_json()["id"]
    second = save(client, admin, audio=audio_url(OGG, "audio/ogg;codecs=opus")).get_json()["id"]
    assert second != first  # a new address, so phones never play a cached old one
    assert [r["id"] for r in client.get("/guide/recordings/ff").get_json()["recordings"]] == [second]
    assert client.get(f"/guide/audio/{first}").status_code == 404
    assert client.get(f"/guide/audio/{second}").mimetype == "audio/ogg"


def test_iphone_recordings_are_kept_too(client):
    admin = new_user("699999999", "admin", "Admin")
    saved = save(client, admin, language="fr", audio=audio_url(MP4, "audio/mp4"))
    assert saved.status_code == 201
    assert client.get(f"/guide/audio/{saved.get_json()['id']}").mimetype == "audio/mp4"


def test_an_admin_removes_a_recording(client):
    admin = new_user("699999999", "admin", "Admin")
    recording_id = save(client, admin).get_json()["id"]
    headers = auth_header(admin, "admin")
    assert client.delete(f"/admin/guide-recordings/{recording_id}", headers=headers).status_code == 200
    assert client.delete(f"/admin/guide-recordings/{recording_id}", headers=headers).status_code == 404
    assert client.get("/guide/recordings/ff").get_json()["recordings"] == []


def test_only_admins_record_or_remove(client):
    seller = new_user("677000001", "seller", "Jean")
    admin = new_user("699999999", "admin", "Admin")
    recording_id = save(client, admin).get_json()["id"]
    assert save(client, seller, role="seller").status_code == 401
    assert client.post("/admin/guide-recordings", json={}).status_code == 401
    assert client.delete(f"/admin/guide-recordings/{recording_id}",
                         headers=auth_header(seller, "seller")).status_code == 401


def test_only_real_recordings_are_kept(client):
    admin = new_user("699999999", "admin", "Admin")
    for bad in ("not a data url", audio_url(b"hello there, not sound", "text/plain"),
                audio_url(OGG, "audio/webm"),                      # Ogg labelled as WebM
                audio_url(WEBM[:4] + b"\x00" * 600_001),           # too long
                audio_url(b"\x1a\x45"),                            # cut short
                "data:audio/webm;base64,@@@@", 42):
        assert save(client, admin, audio=bad).status_code == 400, str(bad)[:40]
    assert save(client, admin, language="xx").status_code == 400
    assert save(client, admin, language="../en").status_code == 400
    assert save(client, admin, text="   ").status_code == 400
    assert save(client, admin, text="x" * 1001).status_code == 400
    assert client.get("/guide/recordings/xx").status_code == 404


def test_the_list_answers_304_while_nothing_changes(client):
    admin = new_user("699999999", "admin", "Admin")
    save(client, admin)
    first = client.get("/guide/recordings/ff")
    etag = first.headers["ETag"]
    assert "no-cache" in first.headers["Cache-Control"]
    assert client.get("/guide/recordings/ff", headers={"If-None-Match": etag}).status_code == 304
    save(client, admin, text="Another sentence.")
    assert client.get("/guide/recordings/ff", headers={"If-None-Match": etag}).status_code == 200


def test_the_studio_can_play_a_recording_before_saving_it():
    assert "media-src 'self' blob:" in CONTENT_SECURITY_POLICY


# ---- On every page ----

PAGES = sorted(name for name in os.listdir(FRONTEND_DIR) if name.endswith(".html"))


def test_every_page_has_the_guide():
    for page in PAGES:
        html = read(page)
        scripts = re.findall(r'<script src="([^"]+)"', html)
        if page == "offline.html":
            assert "js/guide.js" in scripts[-1], page  # the page with no other scripts
            continue
        assert scripts[-2:] == ["js/guide.js", "js/pwa.js"], page
        assert "data-guide=" in html, page


def test_every_stage_named_in_the_pages_has_a_spoken_guide():
    guide = read("js/guide.js")
    named = set()
    for page in PAGES:
        named |= set(re.findall(r'data-guide="([\w.-]+)"', read(page)))
    for script in os.listdir(os.path.join(FRONTEND_DIR, "js")):
        named |= set(re.findall(r'dataset\.guide = "([\w.-]+)"', read(os.path.join("js", script))))
    assert named, "no stages found"
    for stage in named:
        assert re.search(r'"%s":\s*\(\)\s*=>' % re.escape(stage), guide), f"no guide for stage {stage}"


def test_the_guide_never_reads_another_language_with_the_wrong_voice():
    guide = read("js/guide.js")
    # Pidgin is read by an English voice (its words are English-based); no other stand-ins
    assert re.search(r'const STAND_IN_VOICES = \{ wes: "en" \};', guide)


# ---- The computer voice (frontend/voices, made by tools/voice_clips.py) ----

def load_voice_clips():
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "voice_clips.py")
    spec = importlib.util.spec_from_file_location("voice_clips", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_guide_cuts_shown_text_where_the_clips_were_cut():
    voice_clips = load_voice_clips()
    in_guide = re.search(r"const PIECE_BREAK = /(.+)/g;", read("js/guide.js")).group(1)
    assert in_guide == voice_clips.PIECE_BREAK


def test_texts_are_cut_at_numbers_and_placeholders():
    pieces = load_voice_clips().pieces
    assert pieces("Log in") == ["Log in"]
    assert pieces("Price per kg: {price}") == ["Price per kg:"]
    assert pieces("{name} is {distance} away in a straight line.") == ["is", "away in a straight line."]
    assert pieces("Prix : 1 250 FCFA") == ["Prix :", "FCFA"]   # French spaces, a number
    assert pieces("Up to 1,000,000 FCFA per kg") == ["Up to", "FCFA per kg"]
    assert pieces("⁨Jean⁩ arrive") == ["Jean arrive"]          # marks around names in Arabic
    assert pieces("{name}") == [] and pieces(" · ") == []


def test_every_language_of_the_app_has_a_voice_plan():
    voice_clips = load_voice_clips()
    assert set(voice_clips.MODELS) == set(voice_clips.language_names())
    for code in voice_clips.MODELS:
        units = voice_clips.units_of(code)
        assert len(units) > 400, code  # every text of the app, cut into pieces
        assert voice_clips.clean(voice_clips.language_names()[code]) in units  # its own name too
    assert voice_clips.kind_of("coqui:tts_models/lin/openbible/vits") == "coqui"
    assert voice_clips.kind_of("facebook/mms-tts-fub") == "mms"


def test_every_clip_a_voice_lists_is_there():
    voice_clips = load_voice_clips()
    assert voice_clips.check() == []
    voices = os.path.join(FRONTEND_DIR, "voices")
    if not os.path.isdir(voices):
        return
    for code in os.listdir(voices):
        manifest = voice_clips.read_manifest(code) if os.path.isdir(os.path.join(voices, code)) else None
        if manifest:
            assert manifest["language"] == code
            assert manifest["licence"] in ("CC BY-NC 4.0", "CC BY-SA 4.0") and manifest["credit"]
            assert manifest["clips"]
    with open(os.path.join(voices, "names.json"), encoding="utf-8") as f:
        names = json.load(f)
    for code, path in names.items():
        assert path.startswith(f"voices/{code}/") and os.path.exists(os.path.join(FRONTEND_DIR, path))


def test_clips_stay_on_phones_and_their_lists_are_checked_each_visit(client, tmp_path, monkeypatch):
    import app as app_module
    folder = tmp_path / "voices" / "ff"
    folder.mkdir(parents=True)
    (folder / "0123456789abcdef.ogg").write_bytes(b"OggS" + b"\x00" * 40)
    (folder / "index.json").write_text('{"clips": {}}', encoding="utf-8")
    monkeypatch.setattr(app_module, "FRONTEND_DIR", str(tmp_path))
    clip = client.get("/voices/ff/0123456789abcdef.ogg")
    assert clip.status_code == 200 and clip.mimetype in ("audio/ogg", "audio/opus")
    assert "immutable" in clip.headers["Cache-Control"] and "max-age=31536000" in clip.headers["Cache-Control"]
    listing = client.get("/voices/ff/index.json")
    assert listing.status_code == 200 and "immutable" not in listing.headers.get("Cache-Control", "")
    assert client.get("/voices/../app.py").status_code == 404


def test_the_service_worker_keeps_each_clip_once_heard():
    sw = read("sw.js")
    assert r"/^\/voices\/[\w/.-]+\.(json|ogg)$/" in sw
    assert "fetch(isTranslation ? path : request)" in sw  # whole, not the player's Range request
