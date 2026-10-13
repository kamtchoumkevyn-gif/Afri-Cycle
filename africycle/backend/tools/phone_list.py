"""Writes the country list in frontend/js/phone.js from backend/phones.py and the
phonenumbers package, so the pages show the same countries, examples and number
grouping as the server checks. Run it from backend/ after changing the countries in
phones.py or updating phonenumbers (tests/test_phones.py says when it's needed):

    python tools/phone_list.py
"""
import json
import os
import re
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHONE_JS = os.path.join(BACKEND, "..", "frontend", "js", "phone.js")
START, END = "/* COUNTRIES START */", "/* COUNTRIES END */"


def country_list():
    """One entry per country: ISO code, name, calling code, an example number as written
    there, and libphonenumber's groupings [pattern, groups, first digits]. These
    countries group numbers the same way at home and abroad."""
    sys.path.insert(0, BACKEND)
    import phonenumbers
    import phones

    countries = []
    for iso, name in phones.COUNTRIES.items():
        metadata = phonenumbers.PhoneMetadata.metadata_for_region(iso)
        formats = metadata.intl_number_format or metadata.number_format
        countries.append({
            "iso": iso,
            "name": name,
            "code": str(metadata.country_code),
            "example": phones.example(iso),
            "formats": [[f.pattern, re.sub(r"\\(\d)", r"$\1", f.format),
                         f.leading_digits_pattern[-1] if f.leading_digits_pattern else ""]
                        for f in formats if f.format != "NA"],
        })
    return countries


def listed_in_page():
    with open(PHONE_JS, encoding="utf-8") as f:
        source = f.read()
    return json.loads("[" + source.split(START)[1].split(END)[0] + "]")


def write():
    with open(PHONE_JS, encoding="utf-8") as f:
        source = f.read()
    before, rest = source.split(START)
    after = rest.split(END)[1]
    rows = ",\n".join("    " + json.dumps(country, ensure_ascii=False) for country in country_list())
    with open(PHONE_JS, "w", encoding="utf-8") as f:
        f.write(f"{before}{START}\n{rows}\n    {END}{after}")


if __name__ == "__main__":
    write()
    print(f"Updated {os.path.normpath(PHONE_JS)}")
