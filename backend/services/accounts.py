import json
import secrets
import datetime as dt

from database import now
from security import hash_password
from services import portfolio

AGE_BANDS = ["under_13", "13_17", "18_plus", "unknown"]

# placeholder email for accounts made with only a username (can never be typed in the form)
NO_EMAIL = "@no-email.invalid"

GRADES = ["elementary", "middle_school", "high_school", "college", "graduated", "other"]
EXPERIENCE = ["none", "a_little", "some", "lots"]
GOALS = ["learn_basics", "school_project", "save_for_future", "for_fun", "teach_others"]
INTERESTS = ["tech", "gaming", "sports", "food", "fashion", "cars", "entertainment", "energy", "health", "other"]
RELATIONSHIPS = ["mother", "father", "guardian", "grandparent", "other"]


# placeholder username for accounts made with only an email. has a hyphen so nobody can pick it
def placeholder_username():
    return "anon-" + secrets.token_hex(4)


def age_on(birth, today=None):
    today = today or dt.date.today()
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return years


def band_for_age(age):
    if age < 13:
        return "under_13"
    if age < 18:
        return "13_17"
    return "18_plus"


def create_user(db, username, email, password, display_name, age_band, is_demo=False,
                details=None, parent=None):
    cur = db.execute(
        "INSERT INTO users (username, email, password_hash, display_name, age_band, is_demo, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (username, email, hash_password(password), display_name, age_band, 1 if is_demo else 0, now()),
    )
    uid = cur.lastrowid
    portfolio.create_portfolio(db, uid)

    if details:
        db.execute(
            "INSERT INTO user_details (user_id, first_name, last_name, birth_date, country, region, grade, "
            "school, experience, goal, interests, heard_from) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, details["first_name"], details["last_name"], details["birth_date"], details["country"],
             details["region"], details["grade"], details["school"], details["experience"], details["goal"],
             json.dumps(details["interests"]), details["heard_from"]),
        )

    if parent:
        db.execute(
            "INSERT INTO parents (user_id, full_name, relationship, email, phone, consent, consent_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, parent["full_name"], parent["relationship"], parent["email"], parent["phone"],
             1 if parent["consent"] else 0, now()),
        )

    # sort out trading permission
    if age_band == "18_plus":
        # adults do not need a parent
        db.execute(
            "INSERT INTO permissions (user_id, status, requested_at, decided_at, demo_override, note) "
            "VALUES (?, 'approved', ?, ?, 0, 'Adult account, no parent permission needed')",
            (uid, now(), now()),
        )
    elif is_demo:
        # demo kids get the override right away
        db.execute(
            "INSERT INTO permissions (user_id, status, requested_at, decided_at, demo_override, note) "
            "VALUES (?, 'approved', ?, ?, 1, 'DEMO PARENT OVERRIDE. Not real parental consent.')",
            (uid, now(), now()),
        )
    elif parent:
        # real kid account, goes to the parent they listed
        db.execute(
            "INSERT INTO permissions (user_id, status, requested_at, demo_override, note) "
            "VALUES (?, 'pending', ?, 0, ?)",
            (uid, now(), "Waiting for " + parent["full_name"]),
        )
    db.commit()
    return uid


def profile(db, user):
    uid = user["id"]
    s = portfolio.summary(db, uid)
    n_tx = db.execute("SELECT COUNT(*) c FROM transactions WHERE user_id = ?", (uid,)).fetchone()["c"]
    n_watch = db.execute("SELECT COUNT(*) c FROM watchlist WHERE user_id = ?", (uid,)).fetchone()["c"]
    det = db.execute("SELECT * FROM user_details WHERE user_id = ?", (uid,)).fetchone()
    par = db.execute("SELECT * FROM parents WHERE user_id = ?", (uid,)).fetchone()
    return {
        "id": uid,
        "username": None if "-" in user["username"] else user["username"],
        "email": None if user["email"].endswith(NO_EMAIL) else user["email"],
        "display_name": user["display_name"],
        "age_band": user["age_band"],
        "is_demo": bool(user["is_demo"]),
        "created_at": user["created_at"],
        "wallet": s,
        "transactions": n_tx,
        "watchlist_count": n_watch,
        # predictions come later
        "predictions": 0,
        "permission": portfolio.permission_status(db, uid),
        "details": None if not det else {
            "full_name": (det["first_name"] + " " + det["last_name"]).strip(),
            "birth_date": det["birth_date"],
            "country": det["country"],
            "region": det["region"],
            "grade": det["grade"],
            "school": det["school"],
            "experience": det["experience"],
            "goal": det["goal"],
            "interests": json.loads(det["interests"] or "[]"),
        },
        "parent": None if not par else {
            "full_name": par["full_name"],
            "relationship": par["relationship"],
            "email": par["email"],
            "phone": par["phone"],
        },
    }
