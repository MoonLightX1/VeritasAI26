from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database import get_db, now
from deps import current_user
from services import market

router = APIRouter(prefix="/api/notes", tags=["notes"])


class NoteBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(default="", max_length=10000)
    ticker: Optional[str] = None


def clean_ticker(t):
    if not t:
        return None
    t = t.upper()
    if not market.is_company(t):
        raise HTTPException(400, "Unknown company for that note.")
    return t


def as_dict(r):
    return {"id": r["id"], "ticker": r["ticker"], "title": r["title"], "content": r["content"],
            "created_at": r["created_at"], "updated_at": r["updated_at"]}


@router.get("")
def list_notes(q: str = "", ticker: str = "", user=Depends(current_user), db=Depends(get_db)):
    sql = "SELECT * FROM notes WHERE user_id = ?"
    args = [user["id"]]
    if ticker:
        sql += " AND ticker = ?"
        args.append(ticker.upper())
    if q:
        # escape % and _ so they are searched as normal characters
        like = "%" + q[:100].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql += " AND (title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')"
        args += [like, like]
    sql += " ORDER BY updated_at DESC"
    return {"notes": [as_dict(r) for r in db.execute(sql, args).fetchall()]}


@router.post("")
def create(body: NoteBody, user=Depends(current_user), db=Depends(get_db)):
    t = clean_ticker(body.ticker)
    cur = db.execute(
        "INSERT INTO notes (user_id, ticker, title, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user["id"], t, body.title.strip(), body.content, now(), now()),
    )
    db.commit()
    row = db.execute("SELECT * FROM notes WHERE id = ?", (cur.lastrowid,)).fetchone()
    return as_dict(row)


@router.put("/{note_id}")
def update(note_id: int, body: NoteBody, user=Depends(current_user), db=Depends(get_db)):
    t = clean_ticker(body.ticker)
    # user_id check so nobody can edit someone elses note
    cur = db.execute(
        "UPDATE notes SET title = ?, content = ?, ticker = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (body.title.strip(), body.content, t, now(), note_id, user["id"]),
    )
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "Note not found.")
    row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    return as_dict(row)


@router.delete("/{note_id}")
def delete(note_id: int, user=Depends(current_user), db=Depends(get_db)):
    cur = db.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user["id"]))
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "Note not found.")
    return {"ok": True}
