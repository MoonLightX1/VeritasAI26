import re
import sqlite3
import datetime as dt
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

import security
from config import COOKIE_NAME, COOKIE_SECURE, DEMO_MODE
from database import get_db
from deps import current_user
from services import accounts

router = APIRouter(prefix="/api/auth", tags=["auth"])


class ParentBody(BaseModel):
    full_name: str = Field(default="", max_length=80)
    relationship: str = ""
    email: str = ""
    phone: str = Field(default="", max_length=30)
    consent: bool = False


class SignupBody(BaseModel):
    # only the password and a username or email are required, the rest is optional
    first_name: str = Field(default="", max_length=40)
    last_name: str = Field(default="", max_length=40)
    username: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=120)
    password: str = Field(max_length=200)
    confirm_password: str = Field(max_length=200)
    birth_date: str = Field(default="", max_length=20)
    country: str = Field(default="", max_length=60)
    region: str = Field(default="", max_length=60)
    grade: str = Field(default="", max_length=30)
    school: str = Field(default="", max_length=80)
    experience: str = Field(default="", max_length=30)
    goal: str = Field(default="", max_length=30)
    interests: List[str] = Field(default=[], max_length=20)
    heard_from: str = Field(default="", max_length=80)
    accept_terms: bool = False
    demo: bool = False
    parent: Optional[ParentBody] = None


class LoginBody(BaseModel):
    identifier: str = Field(max_length=120)
    password: str = Field(max_length=200)
    remember: bool = False


class NameBody(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)


class PasswordBody(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class DeleteBody(BaseModel):
    password: str = Field(max_length=200)


def set_cookie(response, token, exp, remember):
    kwargs = dict(httponly=True, samesite="strict", secure=COOKIE_SECURE, path="/")
    if remember:
        # only "remember me" gets an expiry
        kwargs["expires"] = exp.strftime("%a, %d %b %Y %H:%M:%S GMT")
    response.set_cookie(COOKIE_NAME, token, **kwargs)


def kill_cookie(response):
    # same flags as when it was set
    response.delete_cookie(COOKIE_NAME, path="/", secure=COOKIE_SECURE, httponly=True, samesite="strict")


def client_ip(request):
    peer = request.client.host if request.client else "unknown"
    # real ip is in the cloudflare header, but only trust it from the tunnel
    if peer in ("127.0.0.1", "::1"):
        cf = request.headers.get("cf-connecting-ip")
        if cf and len(cf) < 64:
            return cf.strip()
    return peer


@router.get("/config")
def config():
    # public, pages check if demo accounts are on
    return {"demo_mode": DEMO_MODE}


@router.get("/username-check")
def username_check(username: str, request: Request, db=Depends(get_db)):
    if security.too_many("uname:" + client_ip(request), limit=120, window=300):
        raise HTTPException(429, "Slow down a bit.")
    if not security.USERNAME_RE.match(username):
        return {"available": False, "reason": "Use 3 to 20 letters, numbers or underscores."}
    row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    return {"available": row is None, "reason": "" if row is None else "That username is taken."}


def check_parent(p, own_email):
    # parent info is optional. returns a clean dict, or None if nothing was filled in
    if p is None:
        return None
    name = p.full_name.strip()
    email = p.email.strip().lower()
    phone = p.phone.strip()
    rel = p.relationship
    if not (name or email or phone or rel):
        return None
    if rel and rel not in accounts.RELATIONSHIPS:
        raise HTTPException(400, "Pick how your parent or guardian is related to you.")
    if email and (not security.EMAIL_RE.match(email) or len(email) > 120):
        raise HTTPException(400, "Your parent or guardian's email does not look right.")
    if email and email == own_email:
        raise HTTPException(400, "Use your parent or guardian's email, not your own.")
    return {"full_name": name, "relationship": rel, "email": email, "phone": phone, "consent": bool(p.consent)}


@router.post("/signup")
def signup(body: SignupBody, request: Request, response: Response, db=Depends(get_db)):
    if security.too_many("signup:" + client_ip(request), limit=15, window=600):
        raise HTTPException(429, "Too many tries, wait a few minutes.")

    username = body.username.strip()
    email = body.email.strip().lower()
    if not username and not email:
        raise HTTPException(400, "Enter a username or an email.")
    if username:
        if not security.USERNAME_RE.match(username):
            raise HTTPException(400, "Username must be 3 to 20 letters, numbers or underscores.")
        if username.lower() == "demo":
            raise HTTPException(400, "That username is taken.")
    if email and (not security.EMAIL_RE.match(email) or len(email) > 120 or email.endswith(accounts.NO_EMAIL)):
        raise HTTPException(400, "That email does not look right.")
    # the database needs both, so a missing one gets a placeholder (shows as N/A in settings)
    if not username:
        username = accounts.placeholder_username()
    if not email:
        email = username.lower() + accounts.NO_EMAIL
    problem = security.password_problem(body.password, "" if "-" in username else username)
    if problem:
        raise HTTPException(400, problem)
    if body.password != body.confirm_password:
        raise HTTPException(400, "Passwords do not match.")

    birth = None
    band = "unknown"
    if body.birth_date.strip():
        try:
            birth = dt.date.fromisoformat(body.birth_date.strip())
        except ValueError:
            raise HTTPException(400, "That birthday does not look right.")
        age = accounts.age_on(birth)
        if age < 6 or age > 110:
            raise HTTPException(400, "That birthday does not look right. You must be at least 6 to sign up.")
        band = accounts.band_for_age(age)

    if body.grade and body.grade not in accounts.GRADES:
        raise HTTPException(400, "Pick your school level.")
    if body.experience and body.experience not in accounts.EXPERIENCE:
        raise HTTPException(400, "Pick how much you know about investing.")
    if body.goal and body.goal not in accounts.GOALS:
        raise HTTPException(400, "Pick what you want to get out of MoneySprout.")
    interests = [i for i in body.interests if i in accounts.INTERESTS]
    if not body.accept_terms:
        raise HTTPException(400, "Please agree to the rules to continue.")

    parent = check_parent(body.parent, email)

    first = body.first_name.strip()
    details = {
        "first_name": first,
        "last_name": body.last_name.strip(),
        "birth_date": birth.isoformat() if birth else "",
        "country": body.country.strip(),
        "region": body.region.strip(),
        "grade": body.grade,
        "school": body.school.strip(),
        "experience": body.experience,
        "goal": body.goal,
        "interests": interests,
        "heard_from": body.heard_from.strip(),
    }
    # what shows in the top bar
    shown = first or ("" if "-" in username else username) or (email.split("@")[0] if not email.endswith(accounts.NO_EMAIL) else "") or "Player"
    try:
        uid = accounts.create_user(db, username, email, body.password, shown, band,
                                   is_demo=True, details=details, parent=parent)
    except sqlite3.IntegrityError:
        db.rollback()
        raise HTTPException(400, "That username or email is already used.")
    token, exp = security.new_session(db, uid, False)
    set_cookie(response, token, exp, False)
    return {"ok": True}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db=Depends(get_db)):
    if security.too_many("login:" + client_ip(request)):
        raise HTTPException(429, "Too many tries, wait a few minutes.")
    ident = body.identifier.strip()[:120]
    # limit per account too
    if security.too_many("login-user:" + ident.lower(), limit=8, window=600):
        raise HTTPException(429, "Too many tries, wait a few minutes.")
    row = db.execute(
        "SELECT * FROM users WHERE username = ? OR email = ?", (ident, ident)
    ).fetchone()
    if not row:
        # still hash so timing does not leak which usernames exist
        security.check_password(body.password[:200], security.DUMMY_HASH)
        raise HTTPException(401, "Wrong username or password.")
    if not security.check_password(body.password[:200], row["password_hash"]):
        raise HTTPException(401, "Wrong username or password.")
    token, exp = security.new_session(db, row["id"], body.remember)
    set_cookie(response, token, exp, body.remember)
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db=Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db.execute("DELETE FROM sessions WHERE token = ?", (security.hash_token(token),))
        db.commit()
    kill_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(user=Depends(current_user), db=Depends(get_db)):
    data = accounts.profile(db, user)
    data["demo_mode"] = DEMO_MODE
    return data


@router.put("/display-name")
def display_name(body: NameBody, user=Depends(current_user), db=Depends(get_db)):
    name = body.display_name.strip()
    if not name:
        raise HTTPException(400, "Name cannot be empty.")
    db.execute("UPDATE users SET display_name = ? WHERE id = ?", (name, user["id"]))
    db.commit()
    return {"ok": True}


@router.put("/password")
def change_password(body: PasswordBody, request: Request, user=Depends(current_user), db=Depends(get_db)):
    if security.too_many("pw:" + str(user["id"]), limit=8, window=600):
        raise HTTPException(429, "Too many tries, wait a few minutes.")
    if not security.check_password(body.current_password, user["password_hash"]):
        raise HTTPException(400, "Current password is wrong.")
    problem = security.password_problem(body.new_password, user["username"])
    if problem:
        raise HTTPException(400, problem)
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?", (security.hash_password(body.new_password), user["id"])
    )
    # log out other devices
    db.execute("DELETE FROM sessions WHERE user_id = ? AND token != ?", (user["id"], security.hash_token(request.cookies.get(COOKIE_NAME, ""))))
    db.commit()
    return {"ok": True}


@router.post("/delete-account")
def delete_account(body: DeleteBody, response: Response, user=Depends(current_user), db=Depends(get_db)):
    if security.too_many("del:" + str(user["id"]), limit=5, window=600):
        raise HTTPException(429, "Too many tries, wait a few minutes.")
    if not security.check_password(body.password, user["password_hash"]):
        raise HTTPException(400, "Password is wrong.")
    db.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    db.commit()
    kill_cookie(response)
    return {"ok": True}
