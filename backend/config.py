import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

# where the sqlite file lives
DB_PATH = os.environ.get("MONEYSPROUT_DB", os.path.join(BASE_DIR, "moneysprout.db"))

# demo mode turns on the parent override and deposits
DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() == "true"

# $10,000 in cents
START_CASH_CENTS = 1000000

SESSION_HOURS = 12
REMEMBER_DAYS = 30

# cookies are https only (we sit behind the cloudflare tunnel)
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() == "true"

# __Host- makes the browser only take the cookie over https. plain name for local testing
COOKIE_NAME = "__Host-ms_session" if COOKIE_SECURE else "ms_session"

# hostnames allowed to hit the app
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "moneysprout.renengine.com")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", PUBLIC_HOST).split(",") if h.strip()]
