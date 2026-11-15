from fastapi import APIRouter, Depends, HTTPException, Response

from database import get_db, now
from deps import current_user
from services import logos, market, predict
import security

router = APIRouter(prefix="/api/stocks", tags=["stocks"])

RANGES = ["1D", "1W", "1M", "3M", "6M", "1Y", "5Y", "MAX"]


def must_exist(ticker):
    if not market.is_company(ticker):
        raise HTTPException(404, "We could not find that company.")
    return ticker.upper()


@router.get("/search")
def search(q: str = "", user=Depends(current_user)):
    return {"results": market.search(q[:50])}


@router.get("/logo/{ticker}")
def get_logo(ticker: str):
    # no login needed, it is only the fixed list of company logos and the landing page shows one
    got = logos.get_logo(ticker)
    if not got:
        raise HTTPException(404, "No logo.")
    return Response(content=got[0], media_type=got[1], headers={"Cache-Control": "private, max-age=604800"})


@router.get("/market/status")
def market_status(user=Depends(current_user)):
    return market.market_status()


@router.get("/{ticker}")
def detail(ticker: str, user=Depends(current_user), db=Depends(get_db)):
    t = must_exist(ticker)
    # remember that they looked at it
    db.execute(
        "INSERT INTO viewed (user_id, ticker, viewed_at) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, ticker) DO UPDATE SET viewed_at = excluded.viewed_at",
        (user["id"], t, now()),
    )
    db.commit()
    data = market.with_quote(t)
    row = db.execute("SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?", (user["id"], t)).fetchone()
    data["watching"] = row is not None
    held = db.execute("SELECT quantity FROM holdings WHERE user_id = ? AND ticker = ?", (user["id"], t)).fetchone()
    data["shares_owned"] = held["quantity"] if held else 0
    return data


@router.get("/{ticker}/quote")
def get_quote(ticker: str, user=Depends(current_user)):
    return market.quote(must_exist(ticker))


@router.get("/{ticker}/history")
def get_history(ticker: str, range: str = "1Y", user=Depends(current_user)):
    t = must_exist(ticker)
    if range not in RANGES:
        raise HTTPException(400, "Bad range.")
    h = market.history(t, range)
    return {
        "ticker": t,
        "range": range,
        "intraday": range in ("1D", "1W"),
        "source": market.SOURCE,
        "timezone": h["timezone"],
        "stale": h["stale"],
        "fetched_at": h["fetched_at"],
        "points": h["points"],
    }


@router.get("/{ticker}/predict")
def get_prediction(ticker: str, range: str = "1Y", user=Depends(current_user)):
    t = must_exist(ticker)
    if range not in RANGES:
        raise HTTPException(400, "Bad range.")
    # news + scoring is heavier than a price fetch, so it gets its own small limit
    if security.too_many("predict:" + str(user["id"]), limit=30, window=60):
        raise HTTPException(429, "Slow down a bit.")
    return predict.predict(t, range)


@router.post("/{ticker}/predict/start")
def start_prediction(ticker: str, range: str = "1Y", user=Depends(current_user)):
    t = must_exist(ticker)
    if range not in RANGES:
        raise HTTPException(400, "Bad range.")
    if security.too_many("predictjob:" + str(user["id"]), limit=10, window=60):
        raise HTTPException(429, "Slow down a bit.")
    jid = predict.start_job(user["id"], t, range)
    if not jid:
        raise HTTPException(429, "You already have predictions running. Wait for them to finish.")
    return {"job": jid}


@router.get("/job/{jid}")
def prediction_job(jid: str, user=Depends(current_user)):
    st = predict.job_state(user["id"], jid)
    if st is None:
        raise HTTPException(404, "That prediction is not running anymore.")
    return st


@router.post("/job/{jid}/cancel")
def cancel_prediction(jid: str, user=Depends(current_user)):
    return {"cancelled": predict.cancel_job(user["id"], jid)}


@router.get("/{ticker}/summary")
def get_summary(ticker: str, range: str = "1Y", user=Depends(current_user)):
    t = must_exist(ticker)
    if range not in RANGES:
        raise HTTPException(400, "Bad range.")
    if security.too_many("summary:" + str(user["id"]), limit=20, window=60):
        raise HTTPException(429, "Slow down a bit.")
    return predict.summary(t, range)
