import os
import sqlite3
import datetime as dt

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    age_band TEXT NOT NULL,
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolios (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    cash_cents INTEGER NOT NULL,
    deposited_cents INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS holdings (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    avg_price REAL NOT NULL,
    PRIMARY KEY (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    type TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    total_cents INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker TEXT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS annotations (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    decided_at TEXT,
    demo_override INTEGER NOT NULL DEFAULT 0,
    note TEXT
);

-- extra stuff we ask for at signup
CREATE TABLE IF NOT EXISTS user_details (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    birth_date TEXT NOT NULL,
    country TEXT NOT NULL,
    region TEXT NOT NULL,
    grade TEXT NOT NULL,
    school TEXT,
    experience TEXT NOT NULL,
    goal TEXT NOT NULL,
    interests TEXT NOT NULL,
    heard_from TEXT
);

CREATE TABLE IF NOT EXISTS parents (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    relationship TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    consent INTEGER NOT NULL,
    consent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS viewed (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    viewed_at TEXT NOT NULL,
    PRIMARY KEY (user_id, ticker)
);
"""


def now():
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


# the database enforces these itself, even if the code forgets
TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS cash_not_negative_ins BEFORE INSERT ON portfolios
WHEN NEW.cash_cents < 0
BEGIN SELECT RAISE(ABORT, 'cash cannot be negative'); END;

CREATE TRIGGER IF NOT EXISTS cash_not_negative_upd BEFORE UPDATE OF cash_cents ON portfolios
WHEN NEW.cash_cents < 0
BEGIN SELECT RAISE(ABORT, 'cash cannot be negative'); END;

CREATE TRIGGER IF NOT EXISTS holding_positive_ins BEFORE INSERT ON holdings
WHEN NEW.quantity <= 0 OR NEW.avg_price < 0
BEGIN SELECT RAISE(ABORT, 'bad holding'); END;

CREATE TRIGGER IF NOT EXISTS holding_positive_upd BEFORE UPDATE ON holdings
WHEN NEW.quantity <= 0 OR NEW.avg_price < 0
BEGIN SELECT RAISE(ABORT, 'bad holding'); END;

CREATE TRIGGER IF NOT EXISTS tx_kind_ins BEFORE INSERT ON transactions
WHEN NEW.type NOT IN ('BUY', 'SELL') OR NEW.quantity <= 0 OR NEW.total_cents < 0
BEGIN SELECT RAISE(ABORT, 'bad transaction'); END;
"""


def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(TRIGGERS)
    # add the deposit column to older databases
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(portfolios)").fetchall()]
    if "deposited_cents" not in cols:
        conn.execute("ALTER TABLE portfolios ADD COLUMN deposited_cents INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    conn.close()
    # owner only (does nothing on windows)
    for suffix in ("", "-wal", "-shm"):
        try:
            os.chmod(DB_PATH + suffix, 0o600)
        except OSError:
            pass


# one connection per request
def get_db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
