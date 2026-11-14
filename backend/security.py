import hashlib
import hmac
import os
import re
import secrets
import threading
import time
import datetime as dt

from config import SESSION_HOURS, REMEMBER_DAYS

ITERATIONS = 600_000


def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return "pbkdf2$%d$%s$%s" % (ITERATIONS, salt.hex(), digest.hex())


def check_password(password, stored):
    try:
        _, iters, salt, digest = stored.split("$")
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(test.hex(), digest)
    except Exception:
        return False


USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# a few of the most used passwords, not a full list but it stops the worst ones
COMMON = {
    "password1", "password12", "password123", "password1234", "passw0rd123", "qwerty12345", "qwertyuiop1",
    "1234567890a", "abcdefghij1", "iloveyou123", "letmein1234", "welcome1234", "admin12345", "moneysprout1",
}


def password_problem(pw, username=""):
    if len(pw) < 10:
        return "Password must be at least 10 characters."
    if len(pw) > 100:
        return "Password is too long."
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"[0-9]", pw):
        return "Password needs at least one letter and one number."
    if pw.lower() in COMMON:
        return "That password is too common, pick another one."
    if username and len(username) >= 3 and username.lower() in pw.lower():
        return "Do not put your username in your password."
    return None


# sessions are stored as a hash, so a leaked database file does not hand out working logins
def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(db, user_id, remember):
    token = secrets.token_urlsafe(32)
    # clean out dead sessions while we are here
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",))
    if remember:
        exp = dt.datetime.utcnow() + dt.timedelta(days=REMEMBER_DAYS)
    else:
        exp = dt.datetime.utcnow() + dt.timedelta(hours=SESSION_HOURS)
    db.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (hash_token(token), user_id, exp.replace(microsecond=0).isoformat() + "Z"),
    )
    db.commit()
    return token, exp


# fake hash so a wrong username takes as long as a wrong password
DUMMY_HASH = hash_password("not-a-real-password-1")

# in memory rate limit. fine for one server process, resets when the app restarts
_hits = {}
_hits_lock = threading.Lock()
MAX_KEYS = 20000


def too_many(key, limit=10, window=300):
    t = time.time()
    with _hits_lock:
        arr = [x for x in _hits.get(key, []) if t - x < window]
        arr.append(t)
        _hits[key] = arr
        # do not let the dict grow forever, even if someone sends tons of random keys
        if len(_hits) > MAX_KEYS // 2:
            for k in list(_hits.keys()):
                if not _hits[k] or t - _hits[k][-1] > 3600:
                    del _hits[k]
            if len(_hits) > MAX_KEYS:
                # still too big, drop the oldest half
                old = sorted(_hits.keys(), key=lambda k: _hits[k][-1] if _hits[k] else 0)
                for k in old[: len(old) // 2]:
                    del _hits[k]
        return len(arr) > limit
