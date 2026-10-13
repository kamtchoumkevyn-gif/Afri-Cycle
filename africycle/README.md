# AFRICYCLE

Recycling our environment, saving our future.

Africycle connects scrap collectors (ferrailleurs) in Cameroon with the buyers near them who pay the best price per kilo, and also covers bulk water and organic waste trading. Payment stays in cash; the app keeps a digital record of every purchase as proof of a fair, traceable trade.

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
- `ADMIN_PHONE_NUMBERS`: the phone number(s) allowed to register as admin, separated by commas

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

### Children and guardians

People under 18 can sell scrap with a parent or guardian watching over the account:

1. On **Create account**, tick **I am under 18**, and fill in the parent or guardian's name, phone number, and relationship. Child accounts are seller accounts.
2. The child can log in, but can't search for buyers, notify them, or send messages until their guardian approves.
3. The guardian registers with the phone number the child typed, choosing **Supervise my child's account**, and logs in to approve or decline. A guardian who already has a buyer or seller account with that number finds the same page under **My children**.
4. After approval, the guardian sees the child's trips on a map, their deliveries and sales, and can read their conversations. Buyers see an **Under 18** badge, and both sides of a chat are told the guardian can read it.

## Phones, tablets and computers

Every page adapts from a 320 px phone to a large desktop screen, upright or sideways, and works by touch, mouse or keyboard.

- **Browsers:** Chrome, Samsung Internet, Opera, Firefox and Edge on Android and computers, and Safari on iPhone and iPad, including phones several years old. A browser too old to run the app shows a notice saying to update it. So does Opera Mini's Extreme data saving, which can't run apps like this; its High or Off setting works.
- **Install it like an app:** on Android, tap **Install Africycle as an app** on the first page (or *Install app* in the browser menu). On iPhone, tap Share, then **Add to Home Screen**. It then opens full screen from its own icon.
- **Weak connections:** after the first visit, pages, styles, scripts, fonts and the map library are kept on the phone (`frontend/sw.js`), so the app opens quickly even when the network is slow. The server also compresses what it sends (Leaflet: 147 KB down to 42 KB). Buyers, prices, messages and locations always come live from the server. When an answer takes more than a few seconds (a weak signal, or the free server waking up), a notice says so instead of the page seeming frozen.
- **No connection:** the app's pages still open and say what couldn't load; an address that was never visited shows a "You're offline" page.
- **Updates:** the server gives `sw.js` a fingerprint of every file in `frontend/`. Each deploy changes it, so phones fetch the new version on their next visit, and any page left open offers **Reload**.
- **Location:** the app asks for GPS first and falls back to the quicker network position when GPS is slow, such as indoors. If location is refused or switched off, it says how to fix that. Browsers only share location over HTTPS (or on `localhost`), so test location features on the deployed site.

To check layouts while developing, use the device toolbar in Chrome's developer tools (Ctrl+Shift+M). To turn the offline copy off for everyone, follow the note at the top of `frontend/sw.js`.

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
    models/            one file per table: database functions only
    routes/            API endpoints grouped by feature
    directions.py      road routes from OpenStreetMap's routing service
    webpush.py         phone notifications (Web Push encryption and signing)
    alerts.py          what the notifications say (new message, seller coming, arrived)
    tests/             pytest suite (conftest.py sets up a fresh test DB)
  frontend/
    index.html, login.html, register.html
    seller-dashboard.html, buyer-dashboard.html, guardian-dashboard.html
    admin-dashboard.html, chat.html, offline.html
    manifest.webmanifest  app name, colours and icons for installing
    sw.js              keeps the app's files on the phone (the server fills in its file list)
    css/               base.css (shared), auth.css, dashboard.css
    js/                shared scripts (see below), one script per page, map.js for the maps,
                       notify.js for unread counts, pop-ups and phone notifications
    fonts/             Archivo ExtraBold for headings (SIL Open Font License)
    icons/             app icons and favicon
    vendor/leaflet/    the map library, served from the site itself
    assets/            Africycle_logo.jpg
```

Every page loads `js/probe.js` and `js/compat.js` (the old-browser check), then `js/api.js` and `js/auth.js`, then its own script, and `js/pwa.js` last. Each shared name is declared once, in one file. Declaring the same `const` in two scripts on one page breaks the second script, and forms then reload the page instead of submitting. Keep `js/compat.js` in old-style JavaScript (no `=>`, `const` or template strings) so that old browsers can run it; if the page scripts start using newer syntax than `js/probe.js` contains, add it there.

## API reference

All routes except `/register`, `/login`, and `/health` need the header `Authorization: Bearer <token>`.

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | /register | anyone | Create an account (name, phoneNumber, password, role: seller, buyer, both, guardian, or admin). Under 18: add `isMinor: true`, guardianName, guardianPhone, guardianRelation |
| POST | /login | anyone | Get a token (phoneNumber, password, optional role) |
| GET | /me | logged in | Own account, guardian status, and number of supervised children |
| GET | /health | anyone | `status` and which `database` is in use |
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
| POST | /push/subscribe | logged in | Turn notifications on for this device (the browser's PushSubscription as JSON) |
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
