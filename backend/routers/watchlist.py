from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import get_db, now
from deps import current_user
from services import market

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class AddBody(BaseModel):
    ticker: str


def watch_items(db, uid):
    rows = db.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY created_at DESC", (uid,)
    ).fetchall()
    out = []
    for r in rows:
        item = market.with_quote(r["ticker"])
        if item:
            item["spark"] = market.spark(r["ticker"])
            out.append(item)
    return out


@router.get("")
def get_watchlist(user=Depends(current_user), db=Depends(get_db)):
    return {"items": watch_items(db, user["id"])}


@router.post("")
def add(body: AddBody, user=Depends(current_user), db=Depends(get_db)):
    t = body.ticker.upper()
    if not market.is_company(t):
        raise HTTPException(404, "We could not find that company.")
    db.execute(
        "INSERT OR IGNORE INTO watchlist (user_id, ticker, created_at) VALUES (?, ?, ?)",
        (user["id"], t, now()),
    )
    db.commit()
    return {"ok": True}


@router.delete("/{ticker}")
def remove(ticker: str, user=Depends(current_user), db=Depends(get_db)):
    db.execute("DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user["id"], ticker.upper()))
    db.commit()
    return {"ok": True}
