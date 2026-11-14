import hashlib
import hmac
import os
import re
import secrets
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


def password_problem(pw):
    if len(pw) < 8:
        return "Password must be at least 8 characters."
    if len(pw) > 100:
        return "Password is too long."
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"[0-9]", pw):
        return "Password needs at least one letter and one number."
    return None


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
        (token, user_id, exp.replace(microsecond=0).isoformat() + "Z"),
    )
    db.commit()
    return token, exp


# fake hash so a wrong username takes as long as a wrong password
DUMMY_HASH = hash_password("not-a-real-password-1")

# very basic in memory rate limit, good enough for a demo
_hits = {}


def too_many(key, limit=10, window=300):
    t = time.time()
    arr = [x for x in _hits.get(key, []) if t - x < window]
    arr.append(t)
    _hits[key] = arr
    # do not let the dict grow forever
    if len(_hits) > 5000:
        for k in list(_hits.keys()):
            if not _hits[k] or t - _hits[k][-1] > 3600:
                del _hits[k]
    return len(arr) > limit
