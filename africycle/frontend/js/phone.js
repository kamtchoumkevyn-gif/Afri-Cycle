// Phone numbers from the 11 countries of Central Africa: the country list on the sign-up
// and log-in pages, and numbers shown the way people write them ("+237 6 77 12 34 56").
// The server checks each number (backend/phones.py, with Google's libphonenumber rules)
// and saves it in international form (+237677123456). The list below comes from the
// same rules; backend/tests/test_phones.py checks that it still matches the server's.

const AfriPhone = (function () {
  const COUNTRY_KEY = "africycle_country"; // the country last chosen on this phone

  // name, calling code, an example number as written in that country, and how numbers
  // are grouped: [pattern, groups, first digits it applies to]
  const COUNTRIES = [
    /* COUNTRIES START */
    {"iso": "CM", "name": "Cameroon", "code": "237", "example": "6 71 23 45 67", "formats": [["(\\d{2})(\\d{2})(\\d{2})(\\d{2})", "$1 $2 $3 $4", "88"], ["(\\d)(\\d{2})(\\d{2})(\\d{2})(\\d{2})", "$1 $2 $3 $4 $5", "[26]|88"]]},
    {"iso": "AO", "name": "Angola", "code": "244", "example": "923 123 456", "formats": [["(\\d{3})(\\d{3})(\\d{3})", "$1 $2 $3", "[29]"]]},
    {"iso": "BI", "name": "Burundi", "code": "257", "example": "79 56 12 34", "formats": [["(\\d{2})(\\d{2})(\\d{2})(\\d{2})", "$1 $2 $3 $4", "[2367]"]]},
    {"iso": "CF", "name": "Central African Republic", "code": "236", "example": "70 01 23 45", "formats": [["(\\d{2})(\\d{2})(\\d{2})(\\d{2})", "$1 $2 $3 $4", "[26-8]"]]},
    {"iso": "TD", "name": "Chad", "code": "235", "example": "63 01 23 45", "formats": [["(\\d{2})(\\d{2})(\\d{2})(\\d{2})", "$1 $2 $3 $4", "[236-9]"]]},
    {"iso": "CG", "name": "Congo", "code": "242", "example": "06 123 4567", "formats": [["(\\d)(\\d{4})(\\d{4})", "$1 $2 $3", "8"], ["(\\d{2})(\\d{3})(\\d{4})", "$1 $2 $3", "[02]"]]},
    {"iso": "CD", "name": "DR Congo", "code": "243", "example": "0991 234 567", "formats": [["(\\d{2})(\\d{2})(\\d{3})", "$1 $2 $3", "88"], ["(\\d{2})(\\d{5})", "$1 $2", "[1-6]"], ["(\\d{2})(\\d{2})(\\d{4})", "$1 $2 $3", "2"], ["(\\d{2})(\\d{3})(\\d{4})", "$1 $2 $3", "1"], ["(\\d{3})(\\d{3})(\\d{3})", "$1 $2 $3", "[89]"], ["(\\d{2})(\\d{2})(\\d{3})(\\d{3})", "$1 $2 $3 $4", "5"]]},
    {"iso": "GQ", "name": "Equatorial Guinea", "code": "240", "example": "222 123 456", "formats": [["(\\d{3})(\\d{3})(\\d{3})", "$1 $2 $3", "[235]"], ["(\\d{3})(\\d{6})", "$1 $2", "[89]"]]},
    {"iso": "GA", "name": "Gabon", "code": "241", "example": "077 12 34 56", "formats": [["(\\d)(\\d{2})(\\d{2})(\\d{2})", "$1 $2 $3 $4", "[2-7]"], ["(\\d{2})(\\d{2})(\\d{2})(\\d{2})", "$1 $2 $3 $4", "0"], ["(\\d{2})(\\d{2})(\\d{2})(\\d{2})", "$1 $2 $3 $4", "11|[67]"]]},
    {"iso": "RW", "name": "Rwanda", "code": "250", "example": "0720 123 456", "formats": [["(\\d{2})(\\d{2})(\\d{2})(\\d{2})", "$1 $2 $3 $4", "0"], ["(\\d{3})(\\d{3})(\\d{3})", "$1 $2 $3", "2"], ["(\\d{3})(\\d{3})(\\d{3})", "$1 $2 $3", "[7-9]"]]},
    {"iso": "ST", "name": "São Tomé and Príncipe", "code": "239", "example": "981 2345", "formats": [["(\\d{3})(\\d{4})", "$1 $2", "[29]"]]}
    /* COUNTRIES END */
  ];

  function byIso(iso) {
    return COUNTRIES.find((country) => country.iso === iso) || null;
  }

  function byCode(code) {
    return COUNTRIES.find((country) => country.code === code) || null;
  }

  // "+237677123456" -> "+237 6 77 12 34 56". Anything else is shown as it is.
  function format(value) {
    const text = String(value == null ? "" : value);
    const match = /^\+(\d{3})(\d+)$/.exec(text);
    const country = match && byCode(match[1]);
    if (!country) return text;
    const national = match[2];
    for (const [pattern, groups, leading] of country.formats) {
      if (leading && !new RegExp(`^(?:${leading})`).test(national)) continue;
      const whole = new RegExp(`^(?:${pattern})$`);
      if (whole.test(national)) return `+${country.code} ${national.replace(whole, groups)}`;
    }
    return `+${country.code} ${national}`;
  }

  function remembered() {
    try {
      const iso = localStorage.getItem(COUNTRY_KEY);
      return byIso(iso) ? iso : null;
    } catch (err) {
      return null;
    }
  }

  function remember(iso) {
    try {
      localStorage.setItem(COUNTRY_KEY, iso);
    } catch (err) {
      // Not remembered on this browser; the list starts at Cameroon next time
    }
  }

  function typedCode(input) {
    const match = /^\s*(?:\+|00)\s*(\d{3})/.exec(input.value);
    return match ? byCode(match[1]) : null;
  }

  // Fills a country list and keeps it, the calling code shown in front of the number and
  // the example in step. Typing a number that starts with +241 (or 00241) picks Gabon.
  // options.follow: another country list to copy until this one is changed by hand.
  function setUp(select, input, codeLabel, options = {}) {
    COUNTRIES.forEach((country) => {
      select.appendChild(new Option(`${country.name} (+${country.code})`, country.iso));
    });
    select.value = (options.follow && options.follow.value) || remembered() || COUNTRIES[0].iso;
    let changedByHand = false;

    function show() {
      const country = byIso(select.value) || COUNTRIES[0];
      codeLabel.textContent = `+${country.code}`;
      codeLabel.hidden = /^\s*(?:\+|00)/.test(input.value); // the number already has one
      input.placeholder = country.example;
    }

    select.addEventListener("change", () => {
      changedByHand = true;
      if (!options.follow) remember(select.value);
      show();
    });
    input.addEventListener("input", () => {
      const country = typedCode(input);
      if (country && country.iso !== select.value) {
        select.value = country.iso;
        changedByHand = true;
        if (!options.follow) remember(country.iso);
      }
      show();
    });
    if (options.follow) {
      options.follow.addEventListener("change", () => {
        if (!changedByHand) {
          select.value = options.follow.value;
          show();
        }
      });
    }
    show();
  }

  return { COUNTRIES, format, setUp };
})();
