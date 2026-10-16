"""Computer voices for the voice guide, in the languages phones can't speak.

Phones have voices for English, French, Arabic and a few more, but not for Fulfulde,
Sango, Lingala or most of Africa's languages. So that the guide (frontend/js/guide.js)
still talks in the person's own language, this makes a short recording (a "clip") of each
of the app's texts in every language that Meta's MMS text-to-speech models speak:

    frontend/voices/<code>/index.json   {"clips": {"text as the app shows it": "id"}, ...}
    frontend/voices/<code>/<id>.ogg     one clip (Opus, mono, 16 kbit/s: a few KB)
    frontend/voices/names.json          each language's name, said in that language

The guide plays a clip only when the phone has no voice of its own for the language, and
a team recording made in the studio (admin page) always comes first. Names, numbers and
messages people type have no clip: those are read by a voice the phone does have.

A text with a number or a {placeholder} in it is cut there, and each piece gets its own
clip ("Price per kg: {price}" -> "Price per kg:"); guide.js cuts the shown text the same
way (PIECE_BREAK, also in guide.js) and fills the gaps with the phone's voice.

The models are big, so GitHub makes the clips (.github/workflows/voices.yml) whenever the
translations change. Only new or changed texts are made again.

Licence: the MMS models are CC BY-NC 4.0, so these clips may not be used commercially.
Before Africycle earns money, replace them with recordings by native speakers (the
studio on the admin page) or with a commercially licensed voice.

Run from backend/ (make needs: pip install torch transformers uroman, and ffmpeg):
    python tools/voice_clips.py plan [codes...]     languages with a model, as JSON
    python tools/voice_clips.py make <code> <model> makes or updates that language's clips
    python tools/voice_clips.py names               writes frontend/voices/names.json
    python tools/voice_clips.py check               every manifest's clips are there
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.normpath(os.path.join(BACKEND, "..", "frontend"))
CATALOGS = os.path.join(FRONTEND, "i18n")
VOICES = os.path.join(FRONTEND, "voices")
I18N_JS = os.path.join(FRONTEND, "js", "i18n.js")

LICENCE = "CC BY-NC 4.0"
SOURCE = "Meta MMS text-to-speech (https://huggingface.co/facebook/mms-tts)"
SEED = 2026
BITRATE = "16k"
# Said the way people say them, not letter by letter (only what is heard changes)
SPOKEN_FORMS = [(re.compile(r"\bFCFA\b"), "sefa"), (re.compile(r"\bkg\b"), "kilo")]

# The MMS model for each app language (ISO 639-3), best first: the first one Hugging Face
# has is used. Fulfulde: Adamawa Fulfulde (Cameroon, Chad, CAR) first. Pidgin: Cameroonian
# Pidgin, else Nigerian Pidgin.
MODELS = {
    "en": ["eng"], "fr": ["fra"], "es": ["spa"], "pt": ["por"], "ar": ["ara", "arb"],
    "zh": ["cmn", "zho"], "sw": ["swh", "swa"], "ha": ["hau"], "yo": ["yor"], "ig": ["ibo"],
    "am": ["amh"], "zu": ["zul"], "af": ["afr"], "so": ["som"], "om": ["gaz", "hae", "orm", "orc"],
    "rw": ["kin"], "rn": ["run"], "ln": ["lin"], "sg": ["sag"],
    "ff": ["fub", "fuv", "fuh", "fuq", "fuc", "fuf", "ffm", "ful"], "wes": ["wes", "pcm"],
}

# Where a shown text is cut into pieces: a {placeholder}, or a number ("1 250", "3.5").
# guide.js has the same pattern; tests/test_voice_guide.py checks they match.
PIECE_BREAK = r"\{\w+\}|[0-9](?:[0-9., ]*[0-9])?"
_BREAK = re.compile(PIECE_BREAK)
_BIDI_MARKS = re.compile("[‎‏⁦-⁩]")  # invisible marks around names in Arabic


def clean(text):
    """Text as guide.js sees it: no direction marks, single spaces."""
    return " ".join(_BIDI_MARKS.sub("", str(text)).split())


def pieces(text):
    """The parts of a text that get a clip: the whole text, or, when it has numbers or
    {placeholders}, the parts between them that have letters."""
    return [part.strip() for part in _BREAK.split(clean(text))
            if part.strip() and any(ch.isalpha() for ch in part)]


def language_names():
    """{code: name} from the language menu in js/i18n.js."""
    with open(I18N_JS, encoding="utf-8") as f:
        source = f.read()
    return dict(re.findall(r'\{ code: "([\w-]+)", name: "([^"]+)"', source))


def texts_of(code):
    """Every text the app shows in this language, and the language's own name."""
    with open(os.path.join(CATALOGS, "fr.json"), encoding="utf-8") as f:
        english = list(json.load(f))
    if code == "en":
        texts = english
    else:
        with open(os.path.join(CATALOGS, f"{code}.json"), encoding="utf-8") as f:
            catalog = json.load(f)
        texts = [catalog.get(key, key) for key in english]
    return texts + [language_names()[code]]


def units_of(code):
    """The distinct pieces to record for a language, in a stable order."""
    seen = {}
    for text in texts_of(code):
        for part in pieces(text):
            seen.setdefault(part, None)
    return list(seen)


def clip_id(model, text):
    return hashlib.sha256(f"{model}\n{text}".encode("utf-8")).hexdigest()[:16]


def manifest_path(code):
    return os.path.join(VOICES, code, "index.json")


def read_manifest(code):
    try:
        with open(manifest_path(code), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---- plan: which languages have a model ----

def model_exists(name):
    request = urllib.request.Request(f"https://huggingface.co/api/models/facebook/mms-tts-{name}",
                                     headers={"User-Agent": "africycle-voice-clips"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status == 200
        except urllib.error.HTTPError as err:
            if err.code in (401, 404):
                return False
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(2 + attempt * 3)
    raise SystemExit(f"Hugging Face did not answer about mms-tts-{name}")


def plan(codes):
    chosen = []
    for code in codes or list(MODELS):
        model = next((f"facebook/mms-tts-{name}" for name in MODELS[code] if model_exists(name)), None)
        if model:
            chosen.append({"code": code, "model": model})
        print(f"{code}: {model or 'no model'}", file=sys.stderr)
    return chosen


# ---- make: the clips of one language ----

def _speaker(model_id):
    """A function text -> (samples as float32 numpy array, sample rate), or None for
    text the model has no letters for."""
    import numpy
    import torch
    from transformers import AutoTokenizer, VitsModel

    torch.set_num_threads(max(1, os.cpu_count() or 1))
    model = VitsModel.from_pretrained(model_id).eval()
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    romanize = None
    if getattr(tokenizer, "is_uroman", False):
        import uroman
        romanizer = uroman.Uroman()
        iso = model_id.rsplit("-", 1)[-1]
        romanize = lambda text: romanizer.romanize_string(text, lcode=iso)  # noqa: E731

    def speak(text):
        for pattern, said in SPOKEN_FORMS:
            text = pattern.sub(said, text)
        spoken = romanize(text) if romanize else text
        inputs = tokenizer(spoken.lower(), return_tensors="pt")
        ids = inputs["input_ids"]
        if ids.shape[-1] == 0 or int((ids != tokenizer.pad_token_id).sum()) == 0:
            return None
        torch.manual_seed(SEED)
        with torch.no_grad():
            samples = model(**inputs).waveform[0].numpy().astype(numpy.float32)
        return samples, model.config.sampling_rate

    return speak


def _tidy(samples, rate):
    """Trims the silence at both ends (keeping 80 ms) and makes it loud enough for a
    phone's speaker."""
    import numpy
    level = numpy.abs(samples)
    if not len(level) or level.max() <= 0:
        return samples
    loud = numpy.nonzero(level > level.max() * 0.02)[0]
    margin = int(rate * 0.08)
    samples = samples[max(0, loud[0] - margin): loud[-1] + margin]
    return (samples * (0.89 / numpy.abs(samples).max())).astype(numpy.float32)


def _encode(samples, rate, path):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(rate), "-ac", "1",
         "-i", "pipe:0", "-c:a", "libopus", "-b:a", BITRATE, "-vbr", "on", "-application", "voip",
         "-map_metadata", "-1", "-f", "ogg", path],
        input=samples.tobytes(), check=True)


def make(code, model):
    folder = os.path.join(VOICES, code)
    os.makedirs(folder, exist_ok=True)
    old = read_manifest(code) or {}
    old_clips = old.get("clips", {}) if old.get("model") == model else {}
    clips, seconds, missing = {}, 0.0, []
    speak = None
    started = time.time()
    for text in units_of(code):
        identifier = clip_id(model, text)
        path = os.path.join(folder, f"{identifier}.ogg")
        if old_clips.get(text) == identifier and os.path.exists(path):
            clips[text] = identifier
            continue
        if speak is None:
            speak = _speaker(model)
        result = speak(text)
        if result is None:
            missing.append(text)
            continue
        samples, rate = result
        samples = _tidy(samples, rate)
        if len(samples) < rate * 0.15:
            missing.append(text)
            continue
        seconds += len(samples) / rate
        _encode(samples, rate, path)
        clips[text] = identifier
    # Clips of texts the app no longer has
    keep = {f"{identifier}.ogg" for identifier in clips.values()} | {"index.json"}
    for name in os.listdir(folder):
        if name not in keep:
            os.remove(os.path.join(folder, name))
    manifest = {"language": code, "model": model, "source": SOURCE, "licence": LICENCE,
                "format": "audio/ogg; codecs=opus", "clips": dict(sorted(clips.items()))}
    with open(manifest_path(code), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=0, sort_keys=False)
        f.write("\n")
    size = sum(os.path.getsize(os.path.join(folder, name)) for name in os.listdir(folder))
    return {"code": code, "model": model, "clips": len(clips), "new_seconds": round(seconds, 1),
            "kilobytes": round(size / 1024), "missing": missing, "minutes": round((time.time() - started) / 60, 1)}


# ---- names, check ----

def names():
    """frontend/voices/names.json: {code: address of the clip of its own name}."""
    result = {}
    for code, name in language_names().items():
        manifest = read_manifest(code)
        identifier = manifest and manifest["clips"].get(clean(name))
        if identifier:
            result[code] = f"voices/{code}/{identifier}.ogg"
    with open(os.path.join(VOICES, "names.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=0, sort_keys=True)
        f.write("\n")
    return result


def check():
    """Problems: clips a manifest names that aren't there, files no manifest names."""
    problems = []
    if not os.path.isdir(VOICES):
        return problems
    for code in sorted(os.listdir(VOICES)):
        folder = os.path.join(VOICES, code)
        if not os.path.isdir(folder):
            continue
        manifest = read_manifest(code)
        if not manifest:
            problems.append(f"{code}: no index.json")
            continue
        named = {f"{identifier}.ogg" for identifier in manifest["clips"].values()}
        present = set(os.listdir(folder)) - {"index.json"}
        problems += [f"{code}: missing {name}" for name in sorted(named - present)]
        problems += [f"{code}: unused {name}" for name in sorted(present - named)]
    return problems


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "plan":
        print(json.dumps(plan(sys.argv[2:])))
    elif command == "make" and len(sys.argv) == 4:
        print(json.dumps(make(sys.argv[2], sys.argv[3]), ensure_ascii=False))
    elif command == "names":
        print(json.dumps(names(), indent=1))
    elif command == "check":
        found = check()
        print("\n".join(found) or "All clips are there.")
        sys.exit(1 if found else 0)
    else:
        print(__doc__)
        sys.exit(2)
