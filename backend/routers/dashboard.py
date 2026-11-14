from fastapi import APIRouter, Depends

from database import get_db
from deps import current_user
from routers.watchlist import watch_items
from services import market
from services import portfolio as pf

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(user=Depends(current_user), db=Depends(get_db)):
    uid = user["id"]
    activity = []
    for r in db.execute(
        "SELECT ticker, type, quantity, price, created_at FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 6",
        (uid,),
    ).fetchall():
        activity.append({"kind": r["type"].lower(), "ticker": r["ticker"], "quantity": r["quantity"],
                         "price": r["price"], "at": r["created_at"]})
    viewed = [
        {"ticker": r["ticker"], "at": r["viewed_at"]}
        for r in db.execute(
            "SELECT ticker, viewed_at FROM viewed WHERE user_id = ? ORDER BY viewed_at DESC LIMIT 5", (uid,)
        ).fetchall()
    ]
    for v in viewed:
        c = market.company(v["ticker"])
        v["name"] = c["name"] if c else v["ticker"]
    return {
        "wallet": pf.summary(db, uid),
        "indices": market.index_quotes(),
        "watchlist": watch_items(db, uid)[:6],
        "trending": market.trending(5),
        "activity": activity,
        "viewed": viewed,
        "data_source": "demo",
    }
