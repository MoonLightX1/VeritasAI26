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
    first_name: str = Field(min_length=1, max_length=40)
    last_name: str = Field(min_length=1, max_length=40)
    username: str
    email: str
    password: str
    confirm_password: str
    birth_date: str
    country: str = Field(min_length=1, max_length=60)
    region: str = Field(min_length=1, max_length=60)
    grade: str
    school: str = Field(default="", max_length=80)
    experience: str
    goal: str
    interests: List[str] = []
    heard_from: str = Field(default="", max_length=80)
    accept_terms: bool = False
    demo: bool = False
    parent: Optional[ParentBody] = None


class LoginBody(BaseModel):
    identifier: str
    password: str
    remember: bool = False


class NameBody(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)


class PasswordBody(BaseModel):
    current_password: str
    new_password: str


class DeleteBody(BaseModel):
    password: str


def set_cookie(response, token, exp, remember):
    kwargs = dict(httponly=True, samesite="lax", secure=COOKIE_SECURE, path="/")
    if remember:
        # only remember sessions get a real expiry, others die with the browser
        kwargs["expires"] = exp.strftime("%a, %d %b %Y %H:%M:%S GMT")
    response.set_cookie(COOKIE_NAME, token, **kwargs)


def client_ip(request):
    return request.client.host if request.client else "unknown"


@router.get("/config")
def config():
    # public, pages use it to know if demo accounts are allowed
    return {"demo_mode": DEMO_MODE}


@router.get("/username-check")
def username_check(username: str, db=Depends(get_db)):
    if not security.USERNAME_RE.match(username):
        return {"available": False, "reason": "Use 3 to 20 letters, numbers or underscores."}
    row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    return {"available": row is None, "reason": "" if row is None else "That username is taken."}


def check_parent(p, own_email):
    # returns a clean dict or raises
    if p is None:
        raise HTTPException(400, "Parent or guardian info is required.")
    name = p.full_name.strip()
    email = p.email.strip().lower()
    phone = p.phone.strip()
    if len(name) < 2:
        raise HTTPException(400, "Enter your parent or guardian's full name.")
    if p.relationship not in accounts.RELATIONSHIPS:
        raise HTTPException(400, "Pick how your parent or guardian is related to you.")
    if not security.EMAIL_RE.match(email) or len(email) > 120:
        raise HTTPException(400, "Your parent or guardian's email does not look right.")
    if email == own_email:
        raise HTTPException(400, "Use your parent or guardian's email, not your own.")
    if len(re.sub(r"\D", "", phone)) < 7:
        raise HTTPException(400, "Enter a phone number for your parent or guardian.")
    if not p.consent:
        raise HTTPException(400, "Your parent or guardian needs to know about this account. Check the box to confirm.")
    return {"full_name": name, "relationship": p.relationship, "email": email, "phone": phone}


@router.post("/signup")
def signup(body: SignupBody, request: Request, response: Response, db=Depends(get_db)):
    if security.too_many("signup:" + client_ip(request), limit=15, window=600):
        raise HTTPException(429, "Too many tries, wait a few minutes.")
    if body.demo and not DEMO_MODE:
        raise HTTPException(403, "Demo mode is off.")

    username = body.username.strip()
    email = body.email.strip().lower()
    if not security.USERNAME_RE.match(username):
        raise HTTPException(400, "Username must be 3 to 20 letters, numbers or underscores.")
    if username.lower() == "demo":
        raise HTTPException(400, "That username is taken.")
    if not security.EMAIL_RE.match(email) or len(email) > 120:
        raise HTTPException(400, "That email does not look right.")
    problem = security.password_problem(body.password)
    if problem:
        raise HTTPException(400, problem)
    if body.password != body.confirm_password:
        raise HTTPException(400, "Passwords do not match.")

    # age comes from the birthday now, not a dropdown
    try:
        birth = dt.date.fromisoformat(body.birth_date)
    except ValueError:
        raise HTTPException(400, "Enter your birthday.")
    age = accounts.age_on(birth)
    if age < 6 or age > 110:
        raise HTTPException(400, "That birthday does not look right. You must be at least 6 to sign up.")
    band = accounts.band_for_age(age)

    if body.grade not in accounts.GRADES:
        raise HTTPException(400, "Pick your school level.")
    if body.experience not in accounts.EXPERIENCE:
        raise HTTPException(400, "Pick how much you know about investing.")
    if body.goal not in accounts.GOALS:
        raise HTTPException(400, "Pick what you want to get out of MoneySprout.")
    interests = [i for i in body.interests if i in accounts.INTERESTS]
    if not interests:
        raise HTTPException(400, "Pick at least one interest.")
    if not body.accept_terms:
        raise HTTPException(400, "Please agree to the rules to continue.")

    # demo accounts always need parent info, real ones only under 18
    parent = None
    if body.demo or band != "18_plus":
        parent = check_parent(body.parent, email)

    details = {
        "first_name": body.first_name.strip(),
        "last_name": body.last_name.strip(),
        "birth_date": birth.isoformat(),
        "country": body.country.strip(),
        "region": body.region.strip(),
        "grade": body.grade,
        "school": body.school.strip(),
        "experience": body.experience,
        "goal": body.goal,
        "interests": interests,
        "heard_from": body.heard_from.strip(),
    }
    try:
        uid = accounts.create_user(db, username, email, body.password, details["first_name"], band,
                                   is_demo=body.demo, details=details, parent=parent)
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
    ident = body.identifier.strip()
    row = db.execute(
        "SELECT * FROM users WHERE username = ? OR email = ?", (ident, ident)
    ).fetchone()
    if not row or not security.check_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Wrong username or password.")
    token, exp = security.new_session(db, row["id"], body.remember)
    set_cookie(response, token, exp, body.remember)
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db=Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(current_user), db=Depends(get_db)):
    data = accounts.profile(db, user)
    data["demo_mode"] = DEMO_MODE
    return data


@router.put("/display-name")
def display_name(body: NameBody, user=Depends(current_user), db=Depends(get_db)):
    db.execute("UPDATE users SET display_name = ? WHERE id = ?", (body.display_name.strip(), user["id"]))
    db.commit()
    return {"ok": True}


@router.put("/password")
def change_password(body: PasswordBody, user=Depends(current_user), db=Depends(get_db)):
    if not security.check_password(body.current_password, user["password_hash"]):
        raise HTTPException(400, "Current password is wrong.")
    problem = security.password_problem(body.new_password)
    if problem:
        raise HTTPException(400, problem)
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?", (security.hash_password(body.new_password), user["id"])
    )
    db.commit()
    return {"ok": True}


@router.post("/delete-account")
def delete_account(body: DeleteBody, response: Response, user=Depends(current_user), db=Depends(get_db)):
    if not security.check_password(body.password, user["password_hash"]):
        raise HTTPException(400, "Password is wrong.")
    db.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}
