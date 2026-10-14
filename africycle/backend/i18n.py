"""The server's messages in the language of the person (or phone) they're for.

Translations are the pages' own files, frontend/i18n/<code>.json, keyed by the English
text, so each language is translated in one place. A message missing from a file is
sent in English.

    _("Invalid phone number or password")            # in the language of this request
    _("Message from {name}", "fr", name="Awa")        # in a given language
    N_("Scrap Iron")                                   # marks text the pages translate

The pages send the chosen language in the Accept-Language header; push notifications
use the language each phone chose (push_subscriptions.language).
"""
import json
import os
import re

from flask import has_request_context, request

FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "i18n")
SOURCE_LANGUAGE = "en"
PLACEHOLDER = re.compile(r"\{(\w+)\}")
_catalogs = {}


def available():
    """Codes of the languages with a translation file, plus English."""
    if "codes" not in _catalogs:
        try:
            names = os.listdir(FOLDER)
        except OSError:
            names = []
        _catalogs["codes"] = [SOURCE_LANGUAGE] + sorted(
            name[:-5] for name in names if name.endswith(".json") and not name.startswith("_"))
    return _catalogs["codes"]


def catalog(code):
    if code not in _catalogs:
        try:
            with open(os.path.join(FOLDER, f"{code}.json"), encoding="utf-8") as f:
                _catalogs[code] = json.load(f)
        except (OSError, ValueError):
            _catalogs[code] = {}
    return _catalogs[code]


def supported(code):
    return code if code in available() else None


def request_language():
    """The language the page asked for, else the browser's, else English."""
    if not has_request_context():
        return SOURCE_LANGUAGE
    best = request.accept_languages.best_match(available())
    if best:
        return best
    for value, _quality in request.accept_languages:  # "fr-CM" when only "fr" is known
        base = value.split("-")[0].lower()
        if base in available():
            return base
    return SOURCE_LANGUAGE


def _(text, language=None, **values):
    language = supported(language) or request_language()
    translated = text if language == SOURCE_LANGUAGE else catalog(language).get(text) or text
    if not values:
        return translated
    return PLACEHOLDER.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), translated)


def N_(text):
    """Marks text that is translated later, where it's shown (e.g. material names)."""
    return text
