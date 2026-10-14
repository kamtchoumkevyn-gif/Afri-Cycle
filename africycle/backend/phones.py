"""Phone numbers from the 11 countries of Central Africa (ECCAS, also called CEEAC).

Numbers are checked against Google's libphonenumber rules (the phonenumbers package, kept
up to date on PyPI). Those rules know each country's lengths, mobile and landline prefixes,
and changes such as Gabon's move to 9 digits. Numbers are saved in international form
(E.164, e.g. +237677123456). So "677 12 34 56", "+237 6 77 12 34 56" and "00237677123456"
all reach the same account, and numbers from two countries can never clash.

frontend/js/phone.js lists the same countries for the sign-up and log-in pages;
tests/test_phones.py checks that the two lists agree.
"""
import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, PhoneNumberType

from i18n import N_, _

# In the order the pages list them: Cameroon first, then A to Z
COUNTRIES = {
    "CM": N_("Cameroon"),
    "AO": N_("Angola"),
    "BI": N_("Burundi"),
    "CF": N_("Central African Republic"),
    "TD": N_("Chad"),
    "CG": N_("Congo"),
    "CD": N_("DR Congo"),
    "GQ": N_("Equatorial Guinea"),
    "GA": N_("Gabon"),
    "RW": N_("Rwanda"),
    "ST": N_("São Tomé and Príncipe"),
}
DEFAULT_COUNTRY = "CM"
CALLABLE = (PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE, PhoneNumberType.FIXED_LINE_OR_MOBILE)
MAX_LENGTH = 40

# An example number per country, shown as it is written there. libphonenumber's own
# example for Gabon is from before 2019, when every number gained a digit.
EXAMPLES = {"GA": "+24177123456"}

# Gabon in 2019: 07 28 01 50 became 077 28 01 50 (+241 77 28 01 50), and so on for each
# old first digit. A number typed the old way is saved the new way, so both find the
# same account.
GABON_NEW_START = {"1": "11", "2": "62", "4": "74", "5": "65", "6": "66", "7": "77"}


class PhoneError(ValueError):
    """A number that can't be used. str(error) says why, in words for the person."""


def _parse(text, country):
    try:
        return phonenumbers.parse(text, country)
    except NumberParseException:
        return None


def _international(number):
    value = phonenumbers.format_number(number, PhoneNumberFormat.E164)
    if value.startswith("+2410") and len(value) == 12 and value[5] in GABON_NEW_START:
        value = "+241" + GABON_NEW_START[value[5]] + value[6:]
    return value


def _usable(number):
    """A real mobile or landline number in one of the 11 countries."""
    return (number is not None and phonenumbers.is_valid_number(number)
            and phonenumbers.region_code_for_number(number) in COUNTRIES
            and phonenumbers.number_type(number) in CALLABLE)


def _clean(text):
    return " ".join(str(text if text is not None else "").split())


def _has_country_code(text):
    return text.startswith(("+", "00"))


def example(country):
    """An example mobile number as people write it in that country, e.g. 6 71 23 45 67."""
    number = (phonenumbers.parse(EXAMPLES[country]) if country in EXAMPLES
              else phonenumbers.example_number_for_type(country, PhoneNumberType.MOBILE))
    return phonenumbers.format_number(number, PhoneNumberFormat.NATIONAL)


def _names(codes):
    return " / ".join(_(COUNTRIES[code]) for code in codes)


def country_code(value):
    """The ISO code sent by a page (e.g. "GA"), or Cameroon when none was sent.
    Raises PhoneError for a country outside the list."""
    code = str(value or DEFAULT_COUNTRY).strip().upper()
    if code not in COUNTRIES:
        raise PhoneError(_("Choose a country from the list"))
    return code


# The messages, for a person's own number and for their guardian's
MESSAGES = {
    False: {
        "missing": N_("Enter your phone number"),
        "long": N_("Your phone number is too long"),
        "abroad": N_("Your phone number is from outside Central Africa. Africycle works with numbers from the countries in the list."),
        "wrong": N_("Check your phone number: {country} numbers look like {example}."),
    },
    True: {
        "missing": N_("Enter your guardian's phone number"),
        "long": N_("Your guardian's phone number is too long"),
        "abroad": N_("Your guardian's phone number is from outside Central Africa. Africycle works with numbers from the countries in the list."),
        "wrong": N_("Check your guardian's phone number: {country} numbers look like {example}."),
    },
}


def normalize(text, country=DEFAULT_COUNTRY, guardian=False):
    """The number in international form, for saving with a new account. Typed as people
    write it at home ("6 77 12 34 56", "077 12 34 56"), with the country chosen on the
    page, or with its country code ("+241 ...", "00241 ..."). guardian: the number is a
    child's guardian's, which the messages say. Raises PhoneError."""
    messages = MESSAGES[bool(guardian)]
    text = _clean(text)
    if not text:
        raise PhoneError(_(messages["missing"]))
    if len(text) > MAX_LENGTH:
        raise PhoneError(_(messages["long"]))
    country = country_code(country)

    number = _parse(text, country)
    if _usable(number):
        return _international(number)

    if number is not None and phonenumbers.is_valid_number(number) and \
            phonenumbers.region_code_for_number(number) not in COUNTRIES:
        raise PhoneError(_(messages["abroad"]))
    message = _(messages["wrong"], country=_(COUNTRIES[country]), example=example(country))
    if not _has_country_code(text):
        # The right number with the wrong country chosen, e.g. a Chad number under Cameroon
        elsewhere = [code for code in COUNTRIES if code != country and _usable(_parse(text, code))]
        if elsewhere:
            message += " " + _("If it's a number from {countries}, choose that country in the list.",
                               countries=_names(elsewhere))
    raise PhoneError(message)


def lookup_forms(text, country=DEFAULT_COUNTRY):
    """Where an account with this number may be saved, most likely first, for logging in:
    the number read for the chosen country (even off the current rules, as some older
    accounts are), then for any other country it fits (in case the wrong one was
    chosen), then as typed (accounts saved before numbers were tidied up)."""
    as_typed = str(text if text is not None else "").strip()
    text = _clean(as_typed)
    if not text or len(text) > MAX_LENGTH:
        return []
    try:
        country = country_code(country)
    except PhoneError:
        country = DEFAULT_COUNTRY
    forms = []
    number = _parse(text, country)
    if number is not None:
        forms.append(_international(number))
    if not _has_country_code(text):
        for code in COUNTRIES:
            other = _parse(text, code)
            if code != country and _usable(other):
                forms.append(_international(other))
    forms.append(as_typed)
    return list(dict.fromkeys(forms))  # without repeats, in order


def stored_form(text, country=DEFAULT_COUNTRY):
    """A number saved before other countries were added (Cameroon digits, or as typed),
    or listed in a setting such as ADMIN_PHONE_NUMBERS, in international form. Left
    as it is when it can't be read as a phone number."""
    cleaned = _clean(text)
    number = _parse(cleaned, country) if cleaned and len(cleaned) <= MAX_LENGTH else None
    if number is None or not phonenumbers.is_possible_number(number):
        return text
    return _international(number)
