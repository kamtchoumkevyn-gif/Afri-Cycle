# AFRICYCLE

Recycling our environment, saving our future.

Africycle connects scrap collectors (ferrailleurs) in Cameroon and the rest of Central Africa with the buyers near them who pay the best price per kilo, and also covers bulk water and organic waste trading. Payment stays in cash; the app keeps a digital record of every purchase as proof of a fair, traceable trade.

Stack: HTML, CSS, and JavaScript on the frontend, with Leaflet and OpenStreetMap for the live maps; Flask (Python) on the backend, with SQLite on your computer and Postgres (Neon) in production; JWT, bcrypt, and rate limiting for security; pytest for tests.

## Run it on your computer (Windows)

Open a terminal in the project folder (the one containing this README), then:

```
python -m venv venv
venv\Scripts\activate
pip install -r backend/requirements.txt
copy .env.example .env
```

Open `.env` and set two values:

- `JWT_SECRET_KEY`: generate one with `python -c "import secrets; print(secrets.token_hex(32))"`
- `ADMIN_PHONE_NUMBERS`: the phone number(s) allowed to register as admin, separated by commas. Cameroon numbers can be written without +237; numbers from other countries need their country code, e.g. `+24177123456`

Leave `DATABASE_URL` empty to keep your data in a local SQLite file.

Start the app:

```
cd backend
python app.py
```

Open **http://localhost:5000** in your browser. Flask serves both the website and the API from that one address, so there is nothing else to start.

On macOS or Linux, use `source venv/bin/activate` and `cp .env.example .env` instead.

## Run the tests

```
cd backend
pytest -v
```

Tests use a temporary database, so they never touch your real data. To run the same tests against a throwaway Postgres database, set `TEST_DATABASE_URL` to its address first; tests wipe that database, so never point it at the real one.

## Try the full flow

1. Register a **buyer**, log in, tap **Save my current location**, set a price for Scrap Iron, and tap **Add photo** in the Photo column to upload a reference picture of the scrap you buy.
2. Log out. Register a **seller**, log in, choose Scrap Iron, and tap **Find buyers**. The map shows you and every buyer, with the best price in orange; tap a buyer for their details and photos.
3. Tap **Route** on a buyer's pin to see the way there by road. Then tap the buyer's **photo** (or **I'm coming**). The buyer is told at once that you are on your way, and your phone shares its location while the trip is in transit.
4. The seller's dashboard now shows **Your trip**: a map with the road route to the buyer, the next turn ("In 300 m, turn left onto Rue Joss"), and the distance and time left. It follows you as you move and works out a new way if you leave the route. Choose **On foot** or **Motorbike or car**. The trip map stays, even after a reload or closing the app, until you tap **I've arrived**; **Google Maps** opens the same destination there.
5. On the buyer's dashboard, **Collectors on their way** shows a map with the seller moving towards their pin.
6. When the seller marks **arrived**, the buyer can mark the delivery **completed** and record the purchase.
7. Register an **admin** with a phone number listed in `ADMIN_PHONE_NUMBERS` to see stats and flag accounts.

Location only works on `localhost` or over HTTPS, which browsers require.

Road routes come from the free OSRM servers that FOSSGIS runs for OpenStreetMap (`routing.openstreetmap.de`, also used by openstreetmap.org). Their rules: at most one request a second, an honest User-Agent, credit beside the route with a "Fix the map" link, and no heavy use. The app's server asks on the phones' behalf, so it can follow those rules: it waits its turn, remembers routes for 10 minutes, and limits each person to 30 routes a minute. If Africycle grows into heavy use, run your own OSRM server and set `ROUTING_URL` to it. When no route can be found, the trip map points a dashed line straight at the buyer and still guides by distance.

### Messages and notifications

- **In the app:** **Messages** shows how many messages are unread, the browser tab shows the count too, e.g. "(2) Seller - Africycle", and a new message pops up with **Open**. Each conversation in the list shows its own count, and opening it marks it read.
- **On the phone:** the dashboards offer **Turn on** notifications. After that, new messages pop up on the phone even when Africycle is closed, and buyers also hear when a seller is coming, is on the way, and has arrived. This works in Chrome, Samsung Internet, Firefox, Edge and Opera on Android and computers. On iPhone and iPad (iOS 16.4 or later) it only works in the app added to the Home Screen; Safari says so. Logging out turns notifications off on that phone.
- **How it works:** standard Web Push, with no Firebase or other account. Each message is encrypted for the receiving phone (RFC 8291) and signed with the app's own key (VAPID, RFC 8292). The server makes that key once and keeps it in the database; to use your own, set `VAPID_PRIVATE_KEY`. The server only sends to the push services of Google, Mozilla, Apple and Microsoft, and forgets a phone when its push service says notifications were turned off there.

### Phone numbers from all of Central Africa

People sign up and log in with a phone number from any of the 11 countries of Central Africa (ECCAS): Cameroon, Angola, Burundi, the Central African Republic, Chad, Congo, DR Congo, Equatorial Guinea, Gabon, Rwanda, and São Tomé and Príncipe.

- **Choosing the country:** the sign-up and log-in pages have a **Country** list (Cameroon to start with, then the last one chosen on that phone). The country's calling code shows in front of the number, with an example written the local way, e.g. 6 71 23 45 67 for Cameroon or 077 12 34 56 for Gabon. Typing a number that starts with a country code, such as +235, picks that country. A child's guardian can live in a different country from the child.
- **Checking:** the server checks each number against Google's libphonenumber rules (the `phonenumbers` package, updated on PyPI as countries change their numbering). It accepts mobile and landline numbers only. When a number doesn't fit, it says what that country's numbers look like, and which country the number does fit, if any. Gabon's numbers from before 2019 (07 28 01 50 instead of 077 28 01 50) are saved in the current form.
- **Saving:** numbers are saved in international form (+237677123456), so "677 12 34 56", "+237 6 77 12 34 56" and "00237677123456" are one and the same account. Pages show numbers grouped the local way: +237 6 77 12 34 56. Logging in also works when the wrong country is chosen.
- **Existing accounts:** the first start after this update turns the Cameroon numbers already saved into +237 numbers (`database/upgrades.py`). Everyone logs in exactly as before.

`frontend/js/phone.js` lists the same countries as `backend/phones.py`. After changing the list, or updating `phonenumbers`, run `python tools/phone_list.py` in `backend/` to refresh the pages' copy; a test fails until it matches.

### Children and guardians

People under 18 can sell scrap with a parent or guardian watching over the account:

1. On **Create account**, tick **I am under 18**, and fill in the parent or guardian's name, phone number, and relationship. Child accounts are seller accounts.
2. The child can log in, but can't search for buyers, notify them, or send messages until their guardian approves.
3. The guardian registers with the phone number the child typed, choosing **Supervise my child's account**, and logs in to approve or decline. A guardian who already has a buyer or seller account with that number finds the same page under **My children**.
4. After approval, the guardian sees the child's trips on a map, their deliveries and sales, and can read their conversations. Buyers see an **Under 18** badge, and both sides of a chat are told the guardian can read it.

## Languages

Africycle comes in 21 languages:

- **Widely used worldwide:** English, French, Spanish, Portuguese, Arabic and Chinese
- **Common in Africa:** Kiswahili, Hausa, Yorùbá, Igbo, Amharic, isiZulu, Afrikaans, Somali, Afaan Oromoo, Ikinyarwanda, Ikirundi, Lingála, Sängö, Fulfulde and Cameroonian Pidgin (Kamtok)

How it works for people:

- **Choosing:** the app opens in the phone's own language when it has it, and in English otherwise. The globe menu at the top of every page switches language, and that phone remembers the choice. For any other language, the menu's last entry, **Other languages...**, explains how to use the browser's Translate.
- **What is translated:** every page, the server's messages, phone notifications (each phone gets them in the language chosen on it), turn-by-turn directions, and the old-browser notice. Numbers, dates and units are written the language's own way, always with the digits 0-9. In Arabic the whole page reads right to left, while phone numbers and maps keep their usual direction.
- **What is not:** names, messages and working hours that people type are shown as they typed them. Material names are stored in English and translated on screen.

Translations are the files in `frontend/i18n/`, one per language (`fr.json`, `sw.json`...), each keyed by the English text. The pages and the server read the same files, and any text missing from a file shows in English.

- **To correct a translation:** edit its file.
- **To translate new text:** first add it to a page, wrap it in `t("...")` in a script, or `_("...")` in the server. Then, in `backend/`, run `python tools/i18n_strings.py` to see how complete each language is, and `python tools/i18n_strings.py --missing fr` to get the texts French still needs, as JSON to fill in. The tests fail until every language has the new text, with the same `{placeholders}`.
- **To add a language:** run `python tools/i18n_strings.py --new > ../frontend/i18n/<code>.json` in `backend/` and translate it. Then add the language to the lists at the top of `frontend/js/i18n.js` and `frontend/js/compat.js`.

The African-language translations are first drafts. Have native speakers check them before relying on them, especially Sängö, Fulfulde, Lingála, Ikirundi, Afaan Oromoo, Igbo and Pidgin. A correction only touches that language's file.

## Phones, tablets and computers

Every page adapts from a 320 px phone to a large desktop screen, upright or sideways, and works by touch, mouse or keyboard.

- **Browsers:** Chrome, Samsung Internet, Opera, Firefox and Edge on Android and computers, and Safari on iPhone and iPad, including phones several years old. A browser too old to run the app shows a notice saying to update it. So does Opera Mini's Extreme data saving, which can't run apps like this; its High or Off setting works.
- **Install it like an app:** on Android, tap **Download the Android app** on the first page for the APK (see [Android app](#android-app)), or **Install Africycle as an app** (or *Install app* in the browser menu). On iPhone, tap Share, then **Add to Home Screen**. It then opens full screen from its own icon.
- **Weak connections:** after the first visit, pages, styles, scripts, fonts and the map library are kept on the phone (`frontend/sw.js`), so the app opens quickly even when the network is slow. The server also compresses what it sends (Leaflet: 147 KB down to 42 KB). Buyers, prices, messages and locations always come live from the server. When an answer takes more than a few seconds (a weak signal, or the free server waking up), a notice says so instead of the page seeming frozen.
- **No connection:** the app's pages still open and say what couldn't load; an address that was never visited shows a "You're offline" page.
- **Updates:** the server gives `sw.js` a fingerprint of every file in `frontend/`. Each deploy changes it, so phones fetch the new version on their next visit, and any page left open offers **Reload**.
- **Location:** the app asks for GPS first and falls back to the quicker network position when GPS is slow, such as indoors. If location is refused or switched off, it says how to fix that. Browsers only share location over HTTPS (or on `localhost`), so test location features on the deployed site.

To check layouts while developing, use the device toolbar in Chrome's developer tools (Ctrl+Shift+M). To turn the offline copy off for everyone, follow the note at the top of `frontend/sw.js`.

## Android app

`android/` is Africycle as an Android app (an APK). It installs on Android 5.0 and newer, which covers about 99.5% of Android phones in use, and opens `https://afri-cycle.onrender.com` full screen from its own icon. The app shows the live website, so every website change reaches it at once, with no app update.

- **With Chrome, Samsung Internet or Edge** (almost every phone): the browser shows the site full screen, without an address bar. This is a *Trusted Web Activity*. The browser first checks `/.well-known/assetlinks.json` on the site, which names the app (`cm.africycle.app`) and the fingerprint of the key it is signed with. Notifications appear as Africycle's own.
- **Without one** (phones without Google services, or with a very old browser): the app shows the site in its built-in screen, which uses Android's WebView. Location, photos from the camera or gallery, phone calls, map links, the back button and screens with a notch all work there. Notifications need a browser, so the built-in screen has none. If the phone's WebView is older than version 55, the app asks to update **Android System WebView**.
- **Permissions:** location, asked the first time a map needs it (approximate is enough), and notifications, asked on Android 13 and newer when they are turned on. Both are under *Settings > Apps > Africycle*. There is no camera permission: photos are taken with the phone's camera app.
- **Security:**
  - The app only uses https.
  - Only Africycle's pages open inside the app. Other links open in the browser or the right app.
  - A link another app sends to a different site opens Africycle's home page instead.
  - Certificate errors stop the page, and Google Safe Browsing checks every page.
  - The login is never copied to backups or to a new phone.
  - Release builds can't be debugged.
- **Languages:** the app's own messages come in the website's 21 languages. Run `python tools/android_strings.py` in `backend/` after changing them.

**Installing on a phone:**

1. On the phone, open the website and tap **Download the Android app** (`/download/android`).
2. Open `Africycle.apk`.
3. If Android asks, allow the browser to install apps (*Install unknown apps*).
4. If Play Protect says it doesn't know the app, choose to install anyway.

**Building and testing:** `.github/workflows/android.yml` runs on every change to `android/` or to `frontend/downloads/`.

- It builds the app and runs Android's checks (lint).
- It installs the app on an emulator of every Android version from 5.0 to the newest. There it opens the app, follows an Africycle link, and tries the security probes. When a change replaces `frontend/downloads/Africycle.apk`, the emulators test that file, the one people download.
- It attaches each screenshot and report, and the overall `*-devices.md` table, to the **android-ci** pre-release. The table also records what the live site gives: `/health`, `assetlinks.json`, and the SHA-256 of the APK behind **Download the Android app**.

To build on a computer, open `android/` in Android Studio, or run `./gradlew assembleRelease` there. `android/tools/make_icons.py` remakes the icons from the website's logo.

### The signing key

Android only lets an app be updated by an APK signed with the same key, and the website's `assetlinks.json` names that key. So keep it for as long as the app exists, and keep it private.

- `africycle-release.p12` (alias `africycle`) and its password were handed to the project owner. Keep two copies outside this repository, for example on a USB key and in a password manager. `.gitignore` keeps `.p12`, `.jks` and `.keystore` files out of commits, and a test checks it.
- Its SHA-256 fingerprint is `D9:A1:78:5C:AC:65:DB:3D:A3:79:6A:DF:09:D3:1C:D2:3B:05:68:CB:30:E9:89:24:30:94:0A:B8:4C:B3:08:6D`. This is the default of `ANDROID_CERT_SHA256` in `backend/app.py`.

**Where the download comes from:** `/download/android` serves `frontend/downloads/Africycle.apk`, the signed APK kept on the site. Version 1.0.0 there has SHA-256 `d7c7712158a40f1bcb7c90104107fbeca0e86b3ae03fa6b02ab88b17b0054419`; a test checks that it is signed with the key above. Without that file, or when `ANDROID_APK_URL` is set, the link goes to `ANDROID_APK_URL`, which by default is the newest GitHub release's `Africycle.apk`.

**To release a new version:**

1. Build it. Either:
   - In the repository's *Settings > Secrets and variables > Actions*, add two secrets once:
     - `ANDROID_KEYSTORE_BASE64`: the key file as text. Get it with `base64 -w0 africycle-release.p12`, or in PowerShell with `[Convert]::ToBase64String([IO.File]::ReadAllBytes("africycle-release.p12"))`.
     - `ANDROID_KEYSTORE_PASSWORD`: its password.

     Then open *Actions > Android app > Run workflow* and enter a version such as `1.0.1`. The workflow builds, signs and tests it, and publishes it as a GitHub release.
   - Or, without the secrets, run the workflow and take `Africycle-unsigned.apk` from the **android-ci** pre-release. Sign it with `apksigner` from Android's build tools and check it:

     ```
     apksigner sign --ks africycle-release.p12 --ks-key-alias africycle --min-sdk-version 21 --out Africycle.apk Africycle-unsigned.apk
     apksigner verify --print-certs Africycle.apk
     ```
2. Replace `frontend/downloads/Africycle.apk` with the new `Africycle.apk` and push. Or delete that file so the link serves the newest GitHub release.

Environment variables on the server, all optional:

- `ANDROID_CERT_SHA256`: the key fingerprints `assetlinks.json` names, separated by commas.
- `ANDROID_PACKAGE`: the app's package name.
- `ANDROID_APK_URL`: where `/download/android` leads instead of the copy on the site.

If the app is ever published on Google Play with Play App Signing, add the fingerprint Play shows (*Test and release > App integrity*) to `ANDROID_CERT_SHA256`. Otherwise copies installed from Play show an address bar.

### Android developer verification (2026–2027)

Google now requires apps on certified Android phones to come from a verified developer. This started on 30 September 2026 in Indonesia, Singapore and Thailand, and Google plans to apply it worldwide in 2027. After that, phones elsewhere, Cameroon included, will only install an APK from an unverified developer through an advanced setup.

Before then, create a **full distribution** account in the Android Developer Console ($25 and an identity check) and register the app `cm.africycle.app` with the signing key above. The free *limited distribution* account (students, hobbyists) only allows 20 devices: enough for the team's own phones, not for users. See [Google's guide](https://support.google.com/android-developer-console/answer/16561738).

## Project structure

```
africycle/
  .env.example         copy to .env; never commit .env
  backend/
    app.py             starts Flask, registers routes, serves the frontend
    config.py          secret key, admin phone list, token lifetime
    extensions.py      rate limiter
    auth_utils.py      reads the logged-in user from the JWT
    database/db.py     SQLite or Postgres connection and all 10 tables
    database/upgrades.py  one-time changes to saved data (e.g. numbers to +237...)
    models/            one file per table: database functions only
    routes/            API endpoints grouped by feature
    phones.py          phone numbers from the 11 Central African countries
    directions.py      road routes from OpenStreetMap's routing service
    webpush.py         phone notifications (Web Push encryption and signing)
    alerts.py          what the notifications say (new message, seller coming, arrived)
    i18n.py            the server's messages in each person's language
    tools/phone_list.py   copies the country list to frontend/js/phone.js
    tools/i18n_strings.py lists every text to translate and checks each language
    tools/android_strings.py  copies the translations into the Android app
    tests/             pytest suite (conftest.py sets up a fresh test DB)
  android/             the Android app (see "Android app"): Gradle project, package cm.africycle.app
    app/src/main/java/cm/africycle/app/  LauncherActivity (opens the site full screen),
                       WebAppActivity (the built-in screen), DelegationService, Site
    ci/                what the GitHub workflow runs: package.sh, device_check.sh
    tools/make_icons.py   the app's icons and splash, from frontend/icons/icon-512.png
  frontend/
    index.html, login.html, register.html
    seller-dashboard.html, buyer-dashboard.html, guardian-dashboard.html
    admin-dashboard.html, chat.html, offline.html
    manifest.webmanifest  app name, colours and icons for installing
    sw.js              keeps the app's files on the phone (the server fills in its file list)
    css/               base.css (shared), auth.css, dashboard.css
    i18n/              translations, one file per language (fr.json, sw.json...)
    js/                shared scripts (see below), one script per page, map.js for the maps,
                       notify.js for unread counts, pop-ups and phone notifications,
                       phone.js for the country list and how numbers are shown,
                       i18n.js for the language: picks it, translates, formats numbers
    fonts/             Archivo ExtraBold for headings (SIL Open Font License)
    icons/             app icons and favicon
    downloads/         Africycle.apk, the signed Android app that /download/android serves
    vendor/leaflet/    the map library, served from the site itself
    assets/            Africycle_logo.jpg
```

Every page loads `js/i18n.js` first, in `<head>`: it picks the language, translates the page before it shows, and provides `t()` for the scripts, which start inside `AfriI18n.whenReady(...)`. Then come `js/probe.js` and `js/compat.js` (the old-browser check), `js/api.js` and `js/auth.js`, the page's own script, and `js/pwa.js` last. Each shared name is declared once, in one file. Declaring the same `const` in two scripts on one page breaks the second script, and forms then reload the page instead of submitting. Keep `js/compat.js` in old-style JavaScript (no `=>`, `const` or template strings) so that old browsers can run it; if the page scripts start using newer syntax than `js/probe.js` contains, add it there.

## API reference

All routes except `/register`, `/login`, and `/health` need the header `Authorization: Bearer <token>`. Phone numbers come back in international form, e.g. `+237677123456`. Messages and directions come in the language named in the `Accept-Language` header (e.g. `fr`, `sw`), and in English otherwise.

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | /register | anyone | Create an account (name, phoneNumber, `country`, password, role: seller, buyer, both, guardian, or admin). `country` is an ISO code from the list (CM, AO, BI, CF, TD, CG, CD, GQ, GA, RW, ST), CM if left out. Under 18: add `isMinor: true`, guardianName, guardianPhone, `guardianCountry` (the child's if left out), guardianRelation |
| POST | /login | anyone | Get a token (phoneNumber, optional `country`, password, optional role) |
| GET | /me | logged in | Own account, guardian status, and number of supervised children |
| GET | /health | anyone | `status` and which `database` is in use |
| GET | /.well-known/assetlinks.json | anyone | Names the Android app and its signing key, so Chrome opens it full screen |
| GET | /download/android | anyone | The Android app (APK): the copy in `frontend/downloads/`, or a redirect to `ANDROID_APK_URL` |
| GET | /material-categories | logged in | List materials for dropdowns |
| GET, POST | /buyer/profile | buyer | Read or save location and working hours |
| GET | /buyer/prices | buyer | List own prices, with photoId |
| POST | /buyer/set-price | buyer | Create or update a price per kg |
| POST | /buyer/material-photo | buyer | Upload a reference photo for a priced material (materialCategoryId, image as a data URL, 400 KB max) |
| DELETE | /buyer/material-photo/<materialId> | buyer | Remove that photo |
| GET | /photos/<id> | logged in | The photo itself |
| POST | /buyer/log-transaction | buyer | Record a cash purchase |
| GET | /buyer/transaction-history | buyer | List own purchases |
| GET | /seller/nearby-buyers | seller | Buyers within a radius, highest price first, with their coordinates |
| GET | /seller/buyer-profile/<id> | seller | A buyer's hours, prices, and photos |
| GET | /seller/contact-buyer/<id> | seller | A buyer's phone number |
| POST | /seller/notify-buyer | seller | Tell a buyer you are coming (buyerId, materialCategoryId; `onTheWay: true` starts the trip in transit) |
| GET | /notifications | buyer or seller | Deliveries you sent or received, with where the buyer is (buyerLatitude, buyerLongitude) |
| PATCH | /notifications/<id>/location | sending seller | Update live location |
| PATCH | /notifications/<id>/status | either party | pending, in transit, arrived, completed |
| GET | /directions?from=lat,lng&to=lat,lng&mode=foot | logged in | Road route (`mode`: foot or car, up to 300 km): distance in metres, duration in seconds, the line, and turn-by-turn steps. 30 a minute |
| GET | /chat/conversations | logged in | People you have messaged, with unread counts |
| GET | /chat/unread | logged in | Unread messages: total, per sender, and the newest one |
| GET | /chat/messages/<userId> | logged in | Messages with one person; marks them read unless `?read=0` |
| POST | /chat/send | logged in | Send a message (also notifies the receiver's phones) |
| GET | /push/key | logged in | The app's public key, which browsers need to turn notifications on |
| POST | /push/subscribe | logged in | Turn notifications on for this device (the browser's PushSubscription as JSON, plus `language`, the language its notifications should come in) |
| DELETE | /push/subscribe | logged in | Turn them off for this device (`endpoint`) |
| GET | /guardian/children | guardian named by the child | Children waiting for approval and children supervised |
| POST | /guardian/children/<id>/approve, /guardian/children/<id>/decline | guardian named by the child | Let the child trade, or not |
| GET | /guardian/children/<id>/activity | the child's guardian | The child's deliveries, sales, and conversations |
| GET | /guardian/children/<id>/messages/<userId> | the child's guardian | One of the child's conversations, read only |
| GET | /admin/stats, /admin/activity-stats, /admin/users, /admin/flagged-accounts | admin | Platform overview |
| POST | /admin/flag-account/<id>, /admin/unflag-account/<id> | admin | Account review |

## Deploy on Render

Create a Web Service from the GitHub repo with:

- Branch: `master`
- Root directory: `africycle/backend` (Render counts from the top of the repository)
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Auto-Deploy: On Commit, so every push to `master` goes live
- Environment variables: `JWT_SECRET_KEY`, `ADMIN_PHONE_NUMBERS`, and `DATABASE_URL`
- Optional: `VAPID_PRIVATE_KEY` (your own notification signing key), `VAPID_SUBJECT` (a `mailto:` address or `https://` page where push services can reach you; the site's address by default), `ROUTING_URL` (your own OSRM server; the app fills in `{coords}`, and `{profile}` with foot or car, e.g. `https://example.org/routed-{profile}/route/v1/driving/{coords}`)

Render may run several copies of the app at once (its `WEB_CONCURRENCY` setting). They share one database and one notification key, and take turns asking the routing service, so that's fine.

After a deploy, open `/health` on the site: `{"status": "ok", "database": "postgres"}` means the new version is live and connected to Neon. If the site keeps showing an older version, open the service's **Events** in Render: a failed deploy leaves the previous version running, and its log ends with the reason.

### Keep data between deploys (free)

Render's free plan wipes local files, including a SQLite database, whenever the app redeploys, restarts, or sleeps after 15 idle minutes. So in production the data lives in a free Neon Postgres database:

1. Create a free account at neon.tech and a project, choosing the region closest to your Render region.
2. Copy the connection string it shows (keep "Connection pooling" on).
3. In Render, open the service's **Environment**, add `DATABASE_URL` with that string, and save. Render redeploys and the app creates its tables on Neon.

To browse or edit the data, use the **Tables** page in the Neon console. Passwords appear as bcrypt hashes, by design. To switch back to SQLite, delete `DATABASE_URL` in Render.

## Deploy on PythonAnywhere (free, keeps data)

PythonAnywhere keeps files between restarts, so the SQLite database stays and no Neon is needed. Updates are not automatic.

1. Sign up for a free Beginner account at eu.pythonanywhere.com (servers in Europe, closer to Cameroon). Your username becomes the address: `username.eu.pythonanywhere.com`.
2. On the **Web** tab: **Add a new web app** → **Manual configuration** → **Python 3.13**.
3. Open a **Bash** console and run this, with the admin phone number(s) at the end:
   ```
   git clone https://github.com/kamtchoumkevyn-gif/Afri-Cycle.git && bash Afri-Cycle/africycle/deploy/pythonanywhere.sh 6XXXXXXXX
   ```
   `deploy/pythonanywhere.sh` installs the packages, writes `.env` with a new secret key, checks that the app starts, and points the web app at it.
4. Press **Reload** on the Web tab and open the address the script prints.

Free PythonAnywhere accounts can only reach websites on its allowlist. Phone notifications to Chrome, Samsung Internet, Edge and iPhones go through, but Firefox's push service and the routing service don't, so on PythonAnywhere the trip map shows a straight line instead of the road route. You can ask PythonAnywhere to add a public service to its allowlist.

To update after changes reach GitHub, run `bash ~/Afri-Cycle/africycle/deploy/pythonanywhere.sh`, then press **Reload**. Free web apps stop after a month unless you click the button on the Web tab that keeps them running. To see the data, download `Afri-Cycle/africycle/backend/database/africycle.db` from the **Files** tab and open it with DB Browser for SQLite.

## Team workflow

Work on your own branch, run `pytest` before pushing, and open a Pull Request into `master`. Never commit `.env`.
