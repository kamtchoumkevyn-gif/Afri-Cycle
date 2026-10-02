# AFRICYCLE

Recycling our environment, saving our future.

Africycle connects scrap collectors (ferrailleurs) in Cameroon with the buyers near them who pay the best price per kilo, and also covers bulk water and organic waste trading. Payment stays in cash; the app keeps a digital record of every purchase as proof of a fair, traceable trade.

Stack: HTML, CSS, and JavaScript on the frontend; Flask (Python) and SQLite on the backend; JWT, bcrypt, and rate limiting for security; pytest for tests.

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

Tests use a temporary database, so they never touch your real data.

## Try the full flow

1. Register a **buyer**, log in, tap **Save my current location**, and set a price for Scrap Iron.
2. Log out. Register a **seller**, log in, choose Scrap Iron, and tap **Find buyers**.
3. Tap **I'm coming** on a buyer, then **Mark in transit**. The buyer now sees the seller's live location.
4. When the seller marks **arrived**, the buyer can mark the delivery **completed** and record the purchase.
5. Register an **admin** with a phone number listed in `ADMIN_PHONE_NUMBERS` to see stats and flag accounts.

Location only works on `localhost` or over HTTPS, which browsers require.

## Project structure

```
africycle/
  .env.example         copy to .env; never commit .env
  backend/
    app.py             starts Flask, registers routes, serves the frontend
    config.py          secret key, admin phone list, token lifetime
    extensions.py      rate limiter
    auth_utils.py      reads the logged-in user from the JWT
    database/db.py     SQLite connection and all 7 tables
    models/            one file per table: database functions only
    routes/            API endpoints grouped by feature
    tests/             pytest suite (conftest.py sets up a fresh test DB)
  frontend/
    index.html, login.html, register.html
    seller-dashboard.html, buyer-dashboard.html, admin-dashboard.html, chat.html
    css/               base.css (shared), auth.css, dashboard.css
    js/                api.js and auth.js load first on every page
    assets/            Africycle_logo.jpg
```

Every page loads `js/api.js`, then `js/auth.js`, then its own script. Each shared name is declared once, in one file. Declaring the same `const` in two scripts on one page breaks the second script, and forms then reload the page instead of submitting.

## API reference

All routes except `/register` and `/login` need the header `Authorization: Bearer <token>`.

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | /register | anyone | Create an account (name, phoneNumber, password, role) |
| POST | /login | anyone | Get a token (phoneNumber, password, optional role) |
| GET | /material-categories | logged in | List materials for dropdowns |
| GET, POST | /buyer/profile | buyer | Read or save location and working hours |
| GET | /buyer/prices | buyer | List own prices |
| POST | /buyer/set-price | buyer | Create or update a price per kg |
| POST | /buyer/log-transaction | buyer | Record a cash purchase |
| GET | /buyer/transaction-history | buyer | List own purchases |
| GET | /seller/nearby-buyers | seller | Buyers within a radius, highest price first |
| GET | /seller/buyer-profile/<id> | seller | A buyer's hours and prices |
| GET | /seller/contact-buyer/<id> | seller | A buyer's phone number |
| POST | /seller/notify-buyer | seller | Tell a buyer you are on your way |
| GET | /notifications | buyer or seller | Deliveries you sent or received |
| PATCH | /notifications/<id>/location | sending seller | Update live location |
| PATCH | /notifications/<id>/status | either party | pending, in transit, arrived, completed |
| GET | /chat/conversations | logged in | People you have messaged |
| GET | /chat/messages/<userId> | logged in | Messages with one person |
| POST | /chat/send | logged in | Send a message |
| GET | /admin/stats, /admin/activity-stats, /admin/users, /admin/flagged-accounts | admin | Platform overview |
| POST | /admin/flag-account/<id>, /admin/unflag-account/<id> | admin | Account review |

## Deploy on Render

Create a Web Service from the GitHub repo with:

- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Environment variables: `JWT_SECRET_KEY` and `ADMIN_PHONE_NUMBERS`

Render's free disk resets on each deploy, so the SQLite data is for demos only.

## Team workflow

Work on your own branch, run `pytest` before pushing, and open a Pull Request into `master`. Never commit `.env`.
