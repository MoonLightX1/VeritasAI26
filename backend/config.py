import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

# where the sqlite file lives
DB_PATH = os.environ.get("MONEYSPROUT_DB", os.path.join(BASE_DIR, "moneysprout.db"))

# demo mode lets the demo login + demo parent override work
DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() == "true"

# 10000 dollars in cents
START_CASH_CENTS = 1000000

SESSION_HOURS = 12
REMEMBER_DAYS = 30

# the site is served over https through the cloudflare tunnel, so cookies are secure
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() == "true"

# the __Host- prefix makes browsers refuse the cookie unless it is secure, on this exact host, with no domain.
# it needs https, so plain http local testing (COOKIE_SECURE=false) uses the normal name
COOKIE_NAME = "__Host-ms_session" if COOKIE_SECURE else "ms_session"

# only these hostnames are allowed to reach the app (comma separated)
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "moneysprout.renengine.com")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", PUBLIC_HOST).split(",") if h.strip()]
