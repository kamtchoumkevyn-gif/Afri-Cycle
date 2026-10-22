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
6. When the seller marks **arrived**, the buyer can mark the delivery **completed** and record the purchase, with photos of the material (**Take a photo**). **Receipt** in the purchase history shows it, and the seller finds it under **Your sales**.
7. Register an **admin** with a phone number listed in `ADMIN_PHONE_NUMBERS`. The first admin is let in straight away; any later admin waits until an existing admin taps **Approve** on their row. The first time, the admin page asks to turn on two-step login with an authenticator app (see [Security](#security)); then it shows stats, accounts to flag, the admin activity log and the voice guide studio.
8. On any page, touch the round speaker button at the bottom to hear what to do there (see [Voice guide](#voice-guide)).

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

### Receipts with photos

Each purchase gets a receipt that both sides can check later.

- **Taking the photos:** while recording a purchase, the buyer taps **Take a photo** (up to 3). The phone's camera opens, and each photo is made smaller on the phone before it is sent.
- **The receipt:** **Receipt** beside each purchase in **Purchase history** shows who sold, what, the weight, the price per kg, the total paid in cash, the date and the photos, with how many photos there are on the button. The buyer can add photos there later, up to 3, or remove one.
- **Who sees it:** the seller sees the same receipts under **Your sales**, and a child seller's guardian sees them in the child's sales. They can look but not change anything. Nobody else can open a receipt.
- **Storage:** the photos are kept in the database, like the price photos, so they survive restarts on Render's free plan.

### Children and guardians

People under 18 can sell scrap with a parent or guardian watching over the account:

1. On **Create account**, tick **I am under 18**, and fill in the parent or guardian's name, phone number, and relationship. Child accounts are seller accounts.
2. The child can log in, but can't search for buyers, notify them, or send messages until their guardian approves. Sign-up, and then the child's page, show a 6-digit **approval code**.
3. The guardian registers with the phone number the child typed, choosing **Supervise my child's account**, logs in, types the code from the child's phone, and approves or declines. A guardian who already has a buyer or seller account with that number finds the same page under **My children**.
   - The code proves the guardian is with the child: phone numbers aren't confirmed, so someone else could register the guardian's number first. After 5 wrong codes the code stops working; the child's page says so and offers **New code**.
4. After approval, the guardian sees the child's trips on a map, their deliveries and sales, and can read their conversations. Buyers see an **Under 18** badge, and both sides of a chat are told the guardian can read it.

## Security

- **Passwords** are stored as bcrypt hashes. Logging in is limited to 5 tries a minute and creating accounts to 10 an hour from one connection. On Render, the app reads each person's real address from Render's proxy (`app.py`), so one person can't use up everyone's tries.
- **Logins** last 24 hours, 8 for admins. Every request checks the account as it is now, so a flagged account is logged out at once and the role always comes from the database, never from the token alone.
- **Flagged accounts are suspended:** they can't log in or use the app until an admin removes the flag. Admin accounts can't be flagged, so admins can't lock each other out.
- **Admins log in in two steps:** password, then the 6-digit code from an authenticator app (Google Authenticator, Microsoft Authenticator or similar; `backend/totp.py`, RFC 6238). The first admin login shows a setup key to add to the app; the admin tools stay closed until a code from it is confirmed. Each code works once. The key is stored encrypted with a key made from `JWT_SECRET_KEY`.
- **Lost phone:** another admin taps **Reset two-step login** on that admin's row, and the admin sets it up again at the next login. If no other admin can, run this in Neon's SQL Editor with the admin's number: `UPDATE users SET "totpEnabled" = 0, "totpSecret" = NULL, "totpLastStep" = NULL WHERE "phoneNumber" = '+237699999999';`. Changing `JWT_SECRET_KEY` makes every saved key unreadable, so all admins would need that reset.
- **Admin activity log:** every admin login, wrong code, flag, removed flag, approved admin, two-step change and voice recording change is saved with the time and address, and shown on the admin page. Nothing in the app edits or deletes it.
- **Phone numbers aren't confirmed by SMS**, so a number alone doesn't prove who someone is. Two rules make up for it where it matters most:
  - **New admins need approval.** The first admin is let in at sign-up. After that, an account registered with a listed number opens no admin tool, not even the two-step setup, until an existing admin taps **Approve** on its row. Until then it can be flagged, in case it isn't who it claims to be. Admins from before this rule stayed approved. Still remove numbers from `ADMIN_PHONE_NUMBERS` once their admin accounts exist.
  - **Guardians type the child's code.** Approving or declining a child needs the 6-digit code shown on the child's phone, so someone who registers the guardian's number first can't take over the child's account. 5 wrong codes stop the code until the child asks for a new one.
  - Confirming every number by SMS would also stop people signing up with someone else's number, at a cost per message.
- **Who sees whom:** buyers with a buying point are public. Any seller sees their prices, buying point and phone number, and can message them. Everyone else (sellers, under-18 sellers, guardians and admins) is seen only by the people they deal with: the other side of a trip or a purchase, or someone they already exchanged messages with. Asking about anyone else answers "not found", so changing a number in a request reveals nothing about other accounts (`backend/access.py`; every route is tried as the wrong person in `tests/test_access.py`, which also fails when a new route with an id has no rule yet).
  - A purchase can only name a collector who told that buyer they were coming, so nobody can put a sale on someone else's record.
  - Suspended buyers disappear from sellers' lists.
  - Until a guardian approves a child, the waiting list shows only the last two digits of the child's number, in case someone else registered the guardian's number.
- **The login secret:** `JWT_SECRET_KEY` signs every login, so anyone who knows or guesses it can log in as anyone. Use a random one of at least 32 characters (for example, the output of `python -c "import secrets; print(secrets.token_urlsafe(48))"`). The admin page shows a red warning while it is shorter. Changing it logs everyone out and makes every admin's saved two-step key unreadable, so reset two-step login for all admins in Neon's SQL Editor as described under **Lost phone**, then each admin sets it up again.
- **Libraries:** `requirements.txt` asks for versions without the known security holes (flask-cors 6.0 or later, gunicorn 22.0 or later), and Render installs the newest versions at each build. The map library, Leaflet 1.9.3, is served from `frontend/vendor/leaflet`; its pop-ups show HTML as given (CVE-2025-69993, not fixed in any release), so the app escapes every name and text in them.
- **Pages** only run the site's own scripts (Content-Security-Policy), everything users type is escaped before it is shown, and database queries always use placeholders.

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

## Voice guide

For people who can't read, or read with difficulty. Every page has a round speaker button at the bottom (bottom left, or bottom right in Arabic). It pulses on the first visit until someone touches it.

- **Touch the speaker button** at any step: it says what the part of the page in view is for and what to do there, in the app's language. An open window, such as a receipt or a buyer's prices, comes first. It also opens a panel with **Listen again**, **Stop**, **Hear before you tap**, **Read messages and directions aloud**, **Speak slowly** and **Voice**.
- **Hear before you tap:** when it is on, the first touch on anything says it, and the second touch uses it.
  - A button says its name, and a text is read.
  - A box to fill says what to type, and a checkbox says whether it is ticked.
  - A list to choose from opens as big spoken choices, with pictures for the materials, and each language is said in its own voice.
  - Something new that appears, such as the trip map or a receipt, explains itself.
  - The setting stays on from page to page on that phone.
- **Read messages and directions aloud:** what appears by itself is said as it appears.
  - The page's messages, such as a wrong password or "Purchase recorded".
  - A new chat message: "Message from Jean", then the message.
  - On a trip to a buyer, each turn when it becomes the next one ("In 300 m, turn left onto..."), again just before it, and the arrival.
  - Turning on **Hear before you tap** turns this on too, since someone who can't read the buttons can't read the messages either. It stays on from page to page on that phone.
- **The words match the screen:** sentences name each button exactly as it reads, in every language, so people can listen for the same words on the button. A test checks it.

**Where the voice comes from,** in this order:

1. **A recording by the team** in that language (see below).
2. **The phone's own voice** for the language. Phones usually have one for English, French, Spanish, Portuguese, Arabic and Chinese, and often for Kiswahili, Afrikaans, Amharic and Hausa, depending on the phone. Pidgin is read by an English voice.
3. **Africycle's computer voice** for the language (see [Computer voices](#computer-voices)): every text of the app, in 17 languages, including Fulfulde, Sängö and Lingála. Names, numbers and typed messages in between are read by a voice the phone has, as in 4.
4. **Otherwise,** a language the phone does have a voice for. The guide tries the phone's own languages first, then French, then English, and the person can choose another under **Voice**. The panel shows the words as they are said. This is what Chinese, Igbo, isiZulu and Afrikaans get on a phone without a voice for them: no open computer voice speaks them yet.

**Recording the guide in a real voice:** the computer voices are understandable but sound like machines, and most of them may not be used to earn money (see below). Native speakers' recordings sound better and replace them at once. On the admin page, **Voice guide recordings** is for this.

- It lists every sentence of the guide (about 60), written in the chosen language with the English below.
- For each one, tap **Record**, say it, tap **Stop**, **Listen**, then **Save**. Recording a sentence again replaces it.
- It needs a microphone, in Chrome or Safari, on a phone or a computer.
- Recordings are kept in the database, up to 30 seconds and 600 KB each. Everyone using that language hears them at once, with no app update.

The recorder can say a sentence in natural words where the written translation sounds wrong; then correct that language's file in `frontend/i18n/` to match.

### Computer voices

`frontend/voices/` holds a short recording (a clip) of every text of the app in 17 languages: English, French, Spanish, Portuguese, Arabic, Kiswahili, Hausa, Yorùbá, Amharic, Somali, Afaan Oromoo, Ikinyarwanda, Ikirundi, Lingála, Sängö, Fulfulde and Pidgin. They are made by computer from the translation files, with open text-to-speech models.

- **When they are used:** only when the phone has no voice of its own for the language, and no team recording of that sentence exists. A text built around a name or a number ("Jean is 2 km away") is said in pieces: the clip of each fixed part, and the name or number in between by a voice the phone has.
- **Size:** about 3 MB per language and 9,500 small files in all, but a phone only downloads the clips it plays (a few KB each), keeps them, and can play them offline afterwards. Clips never change, so browsers keep them for a year.
- **Making them:** GitHub does it (`.github/workflows/voices.yml`, running `backend/tools/voice_clips.py`) whenever a translation file changes, and commits the new clips. Only new or changed texts are made again, in a few minutes. **Actions > Voice guide clips > Run workflow** makes them by hand, for some languages or all.
- **Which voice, and its licence:** each language's `voices/<code>/index.json` names it, and the guide's panel credits it.
  - **Lingála:** Coqui TTS's Open.Bible voice, trained on recordings by Biblica, **CC BY-SA 4.0**: free to use, even commercially, with this credit.
  - **The 16 others:** Meta's MMS models, **CC BY-NC 4.0**: free for this student project, but **not for earning money**. Before Africycle charges anyone, replace them: record the sentences in the studio (a recording always comes first), or switch the language to a commercially licensed voice in `MODELS` in `voice_clips.py`. Coqui also has Open.Bible voices for Hausa and Yorùbá (`tts_models/hau/openbible/vits`, `tts_models/yor/openbible/vits`).
- **Igbo, isiZulu, Afrikaans and Chinese** have no open computer voice yet, so they rely on the phone's voice or the language chosen under **Voice**.

## Phones, tablets and computers

Every page adapts from a 320 px phone to a large desktop screen, upright or sideways, and works by touch, mouse or keyboard.

- **Browsers:** Chrome, Samsung Internet, Opera, Firefox and Edge on Android and computers, and Safari on iPhone and iPad, including phones several years old. A browser too old to run the app shows a notice saying to update it. So does Opera Mini's Extreme data saving, which can't run apps like this; its High or Off setting works.
- **Install it like an app:** on Android, tap **Download the Android app** on the first page for the APK (see [Android app](#android-app)), or **Install Africycle as an app** (or *Install app* in the browser menu). On iPhone, tap Share, then **Add to Home Screen**. It then opens full screen from its own icon.
- **Weak connections:** after the first visit, pages, styles, scripts, fonts and the map library are kept on the phone (`frontend/sw.js`), so the app opens quickly even when the network is slow. The server also compresses what it sends (Leaflet: 147 KB down to 42 KB). Buyers, prices, messages and locations always come live from the server. When an answer takes more than a few seconds (a weak signal, or the free server waking up), a notice says so instead of the page seeming frozen.
- **No connection, or the server waking up** (`frontend/js/api.js`): requests that only read are sent again by themselves for up to 2½ minutes. While the phone is offline they wait for it to come back online, and the notice says so with a **Try again** button. Render's "waking up" page and gateway errors count as no answer. Other requests (sending, saving) are sent again only when Render answered instead of Africycle, so nothing is saved twice. A page that couldn't load at all shows **Try again** under "Can't reach the server", and loads again by itself once the server answers or the phone is back online, unless something is being typed (at most once every 2 minutes).
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
    auth_utils.py      reads the logged-in user from the JWT, checked against the account
    access.py          who may see or message whom (public buyers, people who deal with each other)
    totp.py            admins' two-step login codes (authenticator apps)
    database/db.py     SQLite or Postgres connection and all 13 tables
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
    tools/voice_clips.py  makes the voice guide's computer voices (run by GitHub, see "Computer voices")
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
    voices/            the voice guide's computer voices: per language, index.json and the clips
    js/                shared scripts (see below), one script per page, map.js for the maps,
                       notify.js for unread counts, pop-ups and phone notifications,
                       phone.js for the country list and how numbers are shown,
                       i18n.js for the language: picks it, translates, formats numbers,
                       guide.js for the voice guide, receipt.js for receipts and their photos,
                       studio.js for recording the voice guide (admin page)
    fonts/             Archivo ExtraBold for headings (SIL Open Font License)
    icons/             app icons and favicon
    downloads/         Africycle.apk, the signed Android app that /download/android serves
    vendor/leaflet/    the map library, served from the site itself
    assets/            Africycle_logo.jpg
```

Every page loads `js/i18n.js` first, in `<head>`: it picks the language, translates the page before it shows, and provides `t()` for the scripts, which start inside `AfriI18n.whenReady(...)`. Then come `js/probe.js` and `js/compat.js` (the old-browser check), `js/api.js` and `js/auth.js`, the page's own script, and `js/pwa.js` last. Each shared name is declared once, in one file. Declaring the same `const` in two scripts on one page breaks the second script, and forms then reload the page instead of submitting. Keep `js/compat.js` in old-style JavaScript (no `=>`, `const` or template strings) so that old browsers can run it; if the page scripts start using newer syntax than `js/probe.js` contains, add it there.

## API reference

Routes marked *anyone* need no login; all others need the header `Authorization: Bearer <token>`. Phone numbers come back in international form, e.g. `+237677123456`. Messages and directions come in the language named in the `Accept-Language` header (e.g. `fr`, `sw`), and in English otherwise.

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | /register | anyone | Create an account (name, phoneNumber, `country`, password, role: seller, buyer, both, guardian, or admin). `country` is an ISO code from the list (CM, AO, BI, CF, TD, CG, CD, GQ, GA, RW, ST), CM if left out. Under 18: add `isMinor: true`, guardianName, guardianPhone, `guardianCountry` (the child's if left out), guardianRelation |
| POST | /login | anyone | Get a token (phoneNumber, optional `country`, password, optional role). Admins with two-step login on also send `code`; without it the answer is 401 with `code: "two_step_required"`. A flagged account gets 403 with `code: "suspended"` |
| GET | /me | logged in | Own account, guardian status, and number of supervised children. A child waiting for approval also gets `approvalCode` (the 6 digits the guardian types) and `approvalCodeBlocked` (true after 5 wrong codes) |
| POST | /me/approval-code | a child waiting for approval | A new `approvalCode` (after too many wrong ones) |
| GET | /health | anyone | `status`, which `database` is in use, and on Render the deployed commit (`version`) |
| GET | /ping | anyone | `{"status": "ok"}` without touching the database: for keeping the server awake, and for pages checking the server answers again |
| GET | /.well-known/assetlinks.json | anyone | Names the Android app and its signing key, so Chrome opens it full screen |
| GET | /download/android | anyone | The Android app (APK): the copy in `frontend/downloads/`, or a redirect to `ANDROID_APK_URL` |
| GET | /material-categories | logged in | List materials for dropdowns |
| GET, POST | /buyer/profile | buyer | Read or save location and working hours |
| GET | /buyer/prices | buyer | List own prices, with photoId |
| POST | /buyer/set-price | buyer | Create or update a price per kg |
| POST | /buyer/material-photo | buyer | Upload a reference photo for a priced material (materialCategoryId, image as a data URL, 400 KB max) |
| DELETE | /buyer/material-photo/<materialId> | buyer | Remove that photo |
| GET | /photos/<id> | logged in | The photo itself |
| POST | /buyer/log-transaction | buyer | Record a cash purchase (sellerId: a collector who told you they were coming, materialCategoryId, weightKg, pricePerKg); answers with its `transactionId` |
| GET | /buyer/transaction-history | buyer | List own purchases, with `photoCount` |
| GET | /receipts/<id> | the buyer, the seller, the seller's guardian, admin | A purchase's receipt: names, material, weight, price, total, date and `photoIds`; `canAddPhotos` for the buyer |
| POST | /receipts/<id>/photos | the buyer who recorded it | Add a photo of the material (image as a data URL, 400 KB max, 3 per receipt) |
| DELETE | /receipts/<id>/photos/<photoId> | the buyer who recorded it | Remove that photo |
| GET | /receipt-photos/<id> | those who can see the receipt | The photo itself |
| GET | /seller/sales | seller | Purchases buyers recorded from you, with `photoCount` |
| GET | /seller/nearby-buyers | seller | Buyers within a radius, highest price first, with their coordinates (suspended buyers left out) |
| GET | /seller/buyer-profile/<id> | seller | A buyer's hours, prices, and photos (buyers with a buying point only) |
| GET | /seller/contact-buyer/<id> | seller | A buyer's phone number (buyers with a buying point only; anyone else answers 404) |
| POST | /seller/notify-buyer | seller | Tell a buyer you are coming (buyerId, materialCategoryId; `onTheWay: true` starts the trip in transit) |
| GET | /notifications | buyer or seller | Deliveries you sent or received, with where the buyer is (buyerLatitude, buyerLongitude) |
| PATCH | /notifications/<id>/location | sending seller | Update live location |
| PATCH | /notifications/<id>/status | either party | pending, in transit, arrived, completed |
| GET | /directions?from=lat,lng&to=lat,lng&mode=foot | logged in | Road route (`mode`: foot or car, up to 300 km): distance in metres, duration in seconds, the line, and turn-by-turn steps. 30 a minute |
| GET | /chat/conversations | logged in | People you have messaged, with unread counts |
| GET | /chat/unread | logged in | Unread messages: total, per sender, and the newest one |
| GET | /chat/messages/<userId> | logged in | Messages with one person you deal with (see Security, *Who sees whom*; anyone else answers 404); marks them read unless `?read=0` |
| POST | /chat/send | logged in | Send a message to a buyer with a buying point or someone you deal with (also notifies the receiver's phones) |
| GET | /push/key | logged in | The app's public key, which browsers need to turn notifications on |
| POST | /push/subscribe | logged in | Turn notifications on for this device (the browser's PushSubscription as JSON, plus `language`, the language its notifications should come in) |
| DELETE | /push/subscribe | logged in | Turn them off for this device (`endpoint`) |
| GET | /guardian/children | guardian named by the child | Children waiting for approval (name, relation and `phoneEnd`, the last two digits of their number) and children supervised |
| POST | /guardian/children/<id>/approve, /guardian/children/<id>/decline | guardian named by the child | Let the child trade, or not. Body: `code`, the 6 digits shown on the child's phone; a wrong one answers 400 with `code: "approval_code"` |
| GET | /guardian/children/<id>/activity | the child's guardian | The child's deliveries, sales, and conversations |
| GET | /guardian/children/<id>/messages/<userId> | the child's guardian | One of the child's conversations, read only |
| GET | /admin/stats, /admin/activity-stats, /admin/users, /admin/flagged-accounts | admin | Platform overview; `/admin/stats` also says `weakSecret` when `JWT_SECRET_KEY` is shorter than 32 characters. All admin routes answer 403 with `code: "admin_approval"` until another admin approves a new admin account, then with `code: "two_step_setup"` until the admin turns on two-step login |
| POST | /admin/approve-admin/<id> | admin | Let a new admin account in |
| POST | /admin/flag-account/<id>, /admin/unflag-account/<id> | admin | Account review (a flagged account can't log in; approved admins can't be flagged) |
| GET | /admin/actions | admin | The newest 200 admin actions |
| POST | /admin/two-step/setup | admin, before two-step login is on | A new authenticator key: `secret` and an `otpauth://` `link` |
| POST | /admin/two-step/enable | admin, before two-step login is on | Turn it on with a `code` from the app; returns a new `token` |
| POST | /admin/two-step/reset/<id> | admin | Turn another admin's two-step login off (a lost phone) |
| GET | /guide/recordings/<language> | anyone | The voice guide's sentences recorded in that language: id, text (the English sentence) and mimeType |
| GET | /guide/recorded-languages | anyone | How many sentences are recorded in each language |
| GET | /guide/audio/<id> | anyone | A recording |
| POST | /admin/guide-recordings | admin | Save a recording (language, text: the English sentence, audio as a data URL: WebM, Ogg, MP4, MP3, AAC or WAV, 600 KB max); replaces that sentence's old one |
| DELETE | /admin/guide-recordings/<id> | admin | Remove a recording |

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

**Awake during the day:** Render's free plan puts the server to sleep after 15 minutes without visits, and the next person waits about a minute. GitHub visits `/ping` every 5 minutes from 06:00 to 22:00 Cameroon time (`.github/workflows/keep-awake.yml`), so the app answers at once during the day. `/ping` doesn't open the database, so Neon's free database still sleeps between real visits (its free plan counts the hours it runs). Render's 750 free hours a month are shared by all the free services on one account; this uses about 500. To change the hours, edit the `cron` line (the hours are in UTC, one hour behind Cameroon). GitHub stops schedules in a public repository after 60 days without changes: **Actions > Keep the site awake > Enable workflow** turns it back on. A paid Render instance never sleeps; then this schedule can be deleted.

After a deploy, open `/health` on the site: `{"status": "ok", "database": "postgres", "version": "…"}` means the site is up and connected to Neon, and `version` is the commit Render runs (its `RENDER_GIT_COMMIT`). After each push to `master`, GitHub's **Live site check** (Actions) waits until that commit, or a newer one, is live, then checks the site's files. If the site keeps showing an older version, open the service's **Events** in Render: a failed deploy leaves the previous version running, and its log ends with the reason.

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
