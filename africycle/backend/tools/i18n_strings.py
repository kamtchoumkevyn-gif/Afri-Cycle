"""Every piece of English text Africycle shows, and how complete each translation is.

The text comes from the pages (frontend/*.html: their text, and the placeholder,
aria-label, title and alt attributes, read the same way js/i18n.js translates them),
from the scripts (t("...") in frontend/js), and from the server (_("...") and N_("...")
in backend). Translations are frontend/i18n/<code>.json, keyed by that English text.

Run from backend/:
    python tools/i18n_strings.py               how complete each language is
    python tools/i18n_strings.py --missing fr  the English text French still needs, as JSON
    python tools/i18n_strings.py --new         a file with every text, to start a new language
"""
import ast
import glob
import json
import os
import re
import sys
from html.parser import HTMLParser

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(BACKEND, "..", "frontend")
CATALOGS = os.path.join(FRONTEND, "i18n")
ATTRIBUTES = ("placeholder", "aria-label", "title", "alt")
SKIPPED = ("script", "style", "noscript")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
PLACEHOLDER = re.compile(r"\{(\w+)\}")
JS_CALL = re.compile(r'(?<![\w.$])t\(\s*"((?:[^"\\\n]|\\.)*)"')


def _wanted(text):
    """Text worth translating: it has letters (not "+237", "·" or a number)."""
    return bool(re.search(r"[^\W\d_]", text))


class _PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = set()
        self.stack = []  # (tag, skipped)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        skipped = tag in SKIPPED or attrs.get("translate") == "no" or bool(self.stack and self.stack[-1][1])
        if not skipped:
            for name in ATTRIBUTES:
                value = " ".join((attrs.get(name) or "").split())
                if value and _wanted(value):
                    self.found.add(value)
        if tag not in VOID:
            self.stack.append((tag, skipped))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        text = " ".join(data.split())
        inside_title = any(tag == "title" for tag, _ in self.stack)
        if text and _wanted(text) and (inside_title or not (self.stack and self.stack[-1][1])):
            self.found.add(text)


def page_texts():
    found = set()
    for path in sorted(glob.glob(os.path.join(FRONTEND, "*.html"))):
        parser = _PageText()
        with open(path, encoding="utf-8") as f:
            parser.feed(f.read())
        found |= parser.found
    return found


def _without_comments(source):
    """The script without its /* ... */ comments and its whole-line // comments (which
    is how the app's scripts are written), so examples in comments aren't counted."""
    source = re.sub(r"/\*[\s\S]*?\*/", " ", source)
    return "\n".join(line for line in source.split("\n") if not line.lstrip().startswith("//"))


def script_texts():
    found = set()
    for path in sorted(glob.glob(os.path.join(FRONTEND, "js", "*.js"))):
        with open(path, encoding="utf-8") as f:
            source = _without_comments(f.read())
        for match in JS_CALL.finditer(source):
            found.add(json.loads(f'"{match.group(1)}"'))  # JSON reads JS's escapes (\" \\ \n)
    return found


def server_texts():
    found = set()
    for path in glob.glob(os.path.join(BACKEND, "**", "*.py"), recursive=True):
        if os.sep + "tests" + os.sep in path or os.sep + "tools" + os.sep in path:
            continue
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("_", "N_")
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.add(node.args[0].value)
    return found


def all_texts():
    """Every English text, sorted."""
    return sorted(page_texts() | script_texts() | server_texts())


def catalog_codes():
    return sorted(os.path.basename(path)[:-5] for path in glob.glob(os.path.join(CATALOGS, "*.json"))
                  if not os.path.basename(path).startswith("_"))


def load(code):
    with open(os.path.join(CATALOGS, f"{code}.json"), encoding="utf-8") as f:
        return json.load(f)


def problems(code, texts=None):
    """What's wrong with one language's file: missing or unknown texts, placeholders that
    don't match the English ({name}...), and characters that would break the page's HTML."""
    texts = set(texts if texts is not None else all_texts())
    catalog = load(code)
    found = {"missing": sorted(texts - set(catalog)), "unknown": sorted(set(catalog) - texts),
             "placeholders": [], "unsafe": [], "empty": []}
    for english, translated in catalog.items():
        if not isinstance(translated, str) or not translated.strip():
            found["empty"].append(english)
            continue
        if sorted(PLACEHOLDER.findall(english)) != sorted(PLACEHOLDER.findall(translated)):
            found["placeholders"].append(english)
        if any(char in translated and char not in english for char in '<>&"'):
            found["unsafe"].append(english)
    return found


def main(argv):
    texts = all_texts()
    if argv[:1] == ["--new"]:
        json.dump({text: "" for text in texts}, sys.stdout, ensure_ascii=False, indent=2)
        return 0
    if argv[:1] == ["--missing"] and len(argv) == 2:
        missing = problems(argv[1], texts)["missing"]
        json.dump({text: "" for text in missing}, sys.stdout, ensure_ascii=False, indent=2)
        return 0
    print(f"{len(texts)} texts to translate")
    bad = 0
    for code in catalog_codes():
        found = problems(code, texts)
        done = len(texts) - len(found["missing"])
        notes = ", ".join(f"{len(items)} {kind}" for kind, items in found.items() if items and kind != "missing")
        print(f"  {code:4} {done}/{len(texts)}" + (f"  ({notes})" if notes else ""))
        bad += any(found[kind] for kind in found)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
