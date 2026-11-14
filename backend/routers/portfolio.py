from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import DEMO_MODE
from database import get_db
from deps import current_user
from services import portfolio as pf

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class BuyBody(BaseModel):
    ticker: str
    quantity: Optional[float] = None
    amount: Optional[float] = None


class SellBody(BaseModel):
    ticker: str
    quantity: Optional[float] = None
    sell_all: bool = False


class DepositBody(BaseModel):
    amount: float


class ResetBody(BaseModel):
    confirm: bool = False


# trading needs the parent ok (adults are auto approved)
def need_permission(db, user):
    status = pf.permission_status(db, user["id"])
    if status != "approved":
        msgs = {
            "none": "You need parent permission before you can practice trading. Ask for it in Settings.",
            "pending": "Your permission request is still waiting for a parent.",
            "denied": "Parent permission was denied, so trading is turned off.",
        }
        raise HTTPException(403, msgs.get(status, "Trading is not allowed right now."))


@router.get("")
def get_portfolio(user=Depends(current_user), db=Depends(get_db)):
    data = pf.summary(db, user["id"])
    data["holdings"] = pf.holdings_detail(db, user["id"])
    return data


@router.get("/holdings")
def holdings(user=Depends(current_user), db=Depends(get_db)):
    return {"holdings": pf.holdings_detail(db, user["id"])}


@router.post("/buy")
def buy(body: BuyBody, user=Depends(current_user), db=Depends(get_db)):
    need_permission(db, user)
    try:
        return pf.buy(db, user["id"], body.ticker, body.quantity, body.amount)
    except pf.TradeError as e:
        raise HTTPException(400, str(e))


@router.post("/sell")
def sell(body: SellBody, user=Depends(current_user), db=Depends(get_db)):
    need_permission(db, user)
    try:
        return pf.sell(db, user["id"], body.ticker, body.quantity, body.sell_all)
    except pf.TradeError as e:
        raise HTTPException(400, str(e))


# fake money top up. only in demo mode, and it skips the parent check on purpose
@router.post("/deposit")
def deposit(body: DepositBody, user=Depends(current_user), db=Depends(get_db)):
    if not DEMO_MODE:
        raise HTTPException(403, "Adding pretend money is turned off.")
    try:
        return pf.deposit(db, user["id"], body.amount)
    except pf.TradeError as e:
        raise HTTPException(400, str(e))


@router.get("/transactions")
def transactions(user=Depends(current_user), db=Depends(get_db)):
    rows = db.execute(
        "SELECT id, ticker, type, quantity, price, total_cents, created_at FROM transactions "
        "WHERE user_id = ? ORDER BY id DESC LIMIT 500",
        (user["id"],),
    ).fetchall()
    return {
        "transactions": [
            {"id": r["id"], "ticker": r["ticker"], "type": r["type"], "quantity": r["quantity"],
             "price": r["price"], "total": r["total_cents"] / 100, "created_at": r["created_at"]}
            for r in rows
        ]
    }


@router.post("/reset")
def reset(body: ResetBody, user=Depends(current_user), db=Depends(get_db)):
    if not body.confirm:
        raise HTTPException(400, "Please confirm the reset.")
    pf.reset(db, user["id"])
    return {"ok": True}
