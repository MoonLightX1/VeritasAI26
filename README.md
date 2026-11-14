# MoneySprout (website part)

Stock market learning site with pretend money. This version is the website only. The AI news, sentiment and forecasting parts are not in here yet.

## What works

- Sign up (birthday, school, interests, goals), log in, log out, remember me, change password, delete account
- Demo accounts: you make your own through a form, parent or guardian info is always required
- Light and dark mode (button in the top bar, it remembers your choice)
- Dashboard with wallet, market overview, watchlist, trending, activity
- Search and browse 20 companies
- Stock page with an interactive chart: 1D, 1W, 1M, 3M, 6M, 1Y, 5Y, Max, hover tooltip, volume bars, zoom, pan
- Drawing tools on the chart: pencil, line, price line, date line, arrow, rectangle, circle, text, eraser, colors, undo, redo, clear, save, load
- Buy and sell with $10,000 of virtual cash, portfolio page, transaction history
- Parent permission flow (with a clearly marked demo override)
- Watchlist, notes (with search), settings, portfolio reset
- Download the chart as a PNG image (Download image button on a stock page)

## Important: the prices are fake

There is no live market data connected yet. All prices, charts and index values are simulated by `backend/services/market.py`. The same ticker always gives the same history, so the demo is stable. The site labels this everywhere. When you add a real data API later, replace the functions in that one file.

## Run it

You need Python 3.10 or newer.

```
cd MoneySprout
python -m venv venv
source venv/bin/activate        (on Windows: venv\Scripts\activate)
pip install -r requirements.txt
cd backend
uvicorn main:app --reload
```

Then open http://127.0.0.1:8000

Click "Make a demo account" or sign up. A demo account needs the same info as a normal one, plus parent or guardian info.

The database is a SQLite file at `backend/moneysprout.db`. Delete it to start fresh.

## Settings

Environment variables (set them in your terminal before starting, `.env.example` just lists them):

- `DEMO_MODE` (default true): turns demo account signup and the demo parent override on or off
- `COOKIE_SECURE`: set to true when serving over https
- `MONEYSPROUT_DB`: path to the database file

## Parent permission

Users under 18 give a parent or guardian (name, relationship, email, phone) when they sign up, and a permission request is created for that parent. Users under 18 need that permission before buying or selling. There is no parent account system yet and nothing is emailed, so approving or denying is only possible through the DEMO PARENT OVERRIDE buttons, which only work when `DEMO_MODE=true` and are saved with a demo flag. They are not real consent and nothing here can make a real trade.

## Copying the project

`copy-moneysprout.ps1` (Windows PowerShell) makes a clean copy next to the project folder called `MoneySprout-copy`, skipping anything in `.gitignore` (venv, database, etc).

## Folder layout

```
backend/
  main.py            app setup, serves the frontend
  config.py          settings
  database.py        sqlite tables
  security.py        password hashing, sessions, rate limit
  deps.py            figures out who is logged in
  routers/           api routes (auth, stocks, portfolio, watchlist, notes, annotations, parental, dashboard)
  services/          market data (fake for now), trading logic, accounts
frontend/
  *.html             pages
  css/style.css      all styling
  js/                one file per page, plus app.js (shared), theme.js (light/dark) and chart.js (the chart)
```

## Before real use with kids

Signup collects a lot of personal info, including a parent's contact details. Check child privacy rules (like COPPA) before collecting it from real children. Use fake info while testing. This is a demo.
