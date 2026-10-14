"""The Android app's texts in every language Africycle speaks.

The app's English texts are android/app/src/main/res/values/strings.xml. Their translations
are the website's (frontend/i18n/<code>.json, keyed by the English text), so a text is
translated once for both. This writes them into the app as res/values-<code>/strings.xml.

Run from backend/ after changing a text in values/strings.xml or a translation:
    python tools/android_strings.py           write the values-<code> folders
    python tools/android_strings.py --check   only check they are up to date (exit 1 if not)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import i18n_strings  # noqa: E402

HEADER = ("<!-- Written by backend/tools/android_strings.py from frontend/i18n/{code}.json.\n"
          "     Don't edit: change the translation there, then run the tool. -->\n")


def folder_name(code):
    """Android's name for a language's folder: values-fr, and values-b+wes for a language
    whose code has three letters (Android 5.0 and newer read these)."""
    return f"values-{code}" if len(code) == 2 else f"values-b+{code}"


def android_escape(text):
    """Text as Android string resources want it: quotes and backslashes escaped, < > & as
    XML entities, and a leading @ or ? escaped so it isn't read as a reference."""
    text = text.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n")
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if text.startswith(("@", "?")):
        text = "\\" + text
    return text


def strings_xml(code):
    catalog = i18n_strings.load(code)
    lines = ['<?xml version="1.0" encoding="utf-8"?>', HEADER.format(code=code) + "<resources>"]
    for name, english in i18n_strings.android_strings():
        if english not in catalog:
            raise SystemExit(f"{code}.json has no translation of {english!r} (run tools/i18n_strings.py)")
        lines.append(f'    <string name="{name}">{android_escape(catalog[english])}</string>')
    lines.append("</resources>")
    return "\n".join(lines) + "\n"


def wanted_files():
    """{path: content} of every values-<code>/strings.xml the app should have."""
    return {os.path.join(i18n_strings.ANDROID_RES, folder_name(code), "strings.xml"): strings_xml(code)
            for code in i18n_strings.catalog_codes()}


def out_of_date():
    stale = []
    for path, content in wanted_files().items():
        try:
            with open(path, encoding="utf-8") as f:
                if f.read() == content:
                    continue
        except FileNotFoundError:
            pass
        stale.append(path)
    return stale


def main(argv):
    if argv[:1] == ["--check"]:
        stale = out_of_date()
        for path in stale:
            print("out of date:", os.path.relpath(path, i18n_strings.ANDROID_RES))
        return 1 if stale else 0
    for path, content in wanted_files().items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    print(f"wrote {len(i18n_strings.catalog_codes())} languages into {os.path.relpath(i18n_strings.ANDROID_RES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
