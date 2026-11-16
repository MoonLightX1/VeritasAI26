import datetime as dt

from fastapi import Depends, HTTPException, Request

from config import COOKIE_NAME
from database import get_db
from security import hash_token


# who is logged in, from the cookie
def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if not token or len(token) > 200:
        raise HTTPException(status_code=401, detail="Please log in.")
    row = db.execute(
        "SELECT u.*, s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
        (hash_token(token),),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Please log in.")
    exp = dt.datetime.fromisoformat(row["expires_at"].rstrip("Z"))
    if exp < dt.datetime.utcnow():
        db.execute("DELETE FROM sessions WHERE token = ?", (hash_token(token),))
        db.commit()
        raise HTTPException(status_code=401, detail="Session expired, log in again.")
    return row
