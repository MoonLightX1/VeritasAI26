import json
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import get_db, now
from deps import current_user
from services import market

router = APIRouter(prefix="/api/annotations", tags=["annotations"])

MAX_BYTES = 200_000


class AnnBody(BaseModel):
    shapes: List[Any]


@router.get("/{ticker}")
def load(ticker: str, user=Depends(current_user), db=Depends(get_db)):
    if not market.is_company(ticker):
        raise HTTPException(404, "Unknown company.")
    row = db.execute(
        "SELECT data FROM annotations WHERE user_id = ? AND ticker = ?", (user["id"], ticker.upper())
    ).fetchone()
    return {"shapes": json.loads(row["data"]) if row else []}


@router.put("/{ticker}")
def save(ticker: str, body: AnnBody, user=Depends(current_user), db=Depends(get_db)):
    if not market.is_company(ticker):
        raise HTTPException(404, "Unknown company.")
    data = json.dumps(body.shapes)
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "Too many drawings, clear some and try again.")
    db.execute(
        "INSERT INTO annotations (user_id, ticker, data, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, ticker) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
        (user["id"], ticker.upper(), data, now()),
    )
    db.commit()
    return {"ok": True, "count": len(body.shapes)}
