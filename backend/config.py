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
COOKIE_NAME = "ms_session"

# set this to true if you put it behind https
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
