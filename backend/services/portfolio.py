from database import now
from config import START_CASH_CENTS
from services import market


class TradeError(Exception):
    pass


def create_portfolio(db, user_id):
    db.execute(
        "INSERT INTO portfolios (user_id, cash_cents, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (user_id, START_CASH_CENTS, now(), now()),
    )


def permission_status(db, user_id):
    # latest row wins, no row means nothing asked yet
    row = db.execute(
        "SELECT * FROM permissions WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
    ).fetchone()
    return row["status"] if row else "none"


def get_cash_cents(db, user_id):
    row = db.execute("SELECT cash_cents FROM portfolios WHERE user_id = ?", (user_id,)).fetchone()
    return row["cash_cents"]


def holdings_detail(db, user_id):
    rows = db.execute("SELECT * FROM holdings WHERE user_id = ? ORDER BY ticker", (user_id,)).fetchall()
    out = []
    for r in rows:
        q = market.quote(r["ticker"])
        c = market.company(r["ticker"])
        value = r["quantity"] * q["price"]
        cost = r["quantity"] * r["avg_price"]
        out.append({
            "ticker": r["ticker"],
            "name": c["name"] if c else r["ticker"],
            "quantity": r["quantity"],
            "avg_price": round(r["avg_price"], 2),
            "price": q["price"],
            "value": round(value, 2),
            "cost": round(cost, 2),
            "profit": round(value - cost, 2),
            "profit_pct": round((value - cost) / cost * 100, 2) if cost else 0,
            "day_change": round(r["quantity"] * q["change"], 2),
        })
    return out


def summary(db, user_id):
    cash = get_cash_cents(db, user_id) / 100
    hold = holdings_detail(db, user_id)
    invested = sum(h["cost"] for h in hold)
    holdings_value = sum(h["value"] for h in hold)
    day_change = sum(h["day_change"] for h in hold)
    total = cash + holdings_value
    start = START_CASH_CENTS / 100
    prev_total = total - day_change
    return {
        "cash": round(cash, 2),
        "holdings_value": round(holdings_value, 2),
        "invested": round(invested, 2),
        "total_value": round(total, 2),
        "profit": round(total - start, 2),
        "profit_pct": round((total - start) / start * 100, 2),
        "day_change": round(day_change, 2),
        "day_change_pct": round(day_change / prev_total * 100, 2) if prev_total else 0,
        "starting_cash": start,
    }


def buy(db, user_id, ticker, quantity=None, amount=None):
    ticker = ticker.upper()
    if not market.is_company(ticker):
        raise TradeError("Unknown company.")
    price = market.price_at(ticker)
    if quantity is None and amount is None:
        raise TradeError("Enter a number of shares or an amount.")
    if quantity is None:
        if amount <= 0:
            raise TradeError("Amount must be more than zero.")
        quantity = round(amount / price, 4)
    quantity = round(quantity, 4)
    if quantity <= 0:
        raise TradeError("Quantity must be more than zero.")
    if quantity > 1_000_000:
        raise TradeError("That is too many shares.")
    total_cents = int(round(quantity * price * 100))
    if total_cents <= 0:
        raise TradeError("That is too small to buy.")
    cash = get_cash_cents(db, user_id)
    if total_cents > cash:
        raise TradeError("Not enough virtual cash for that.")
    row = db.execute(
        "SELECT * FROM holdings WHERE user_id = ? AND ticker = ?", (user_id, ticker)
    ).fetchone()
    if row:
        new_q = row["quantity"] + quantity
        new_avg = (row["quantity"] * row["avg_price"] + quantity * price) / new_q
        db.execute(
            "UPDATE holdings SET quantity = ?, avg_price = ? WHERE user_id = ? AND ticker = ?",
            (round(new_q, 4), new_avg, user_id, ticker),
        )
    else:
        db.execute(
            "INSERT INTO holdings (user_id, ticker, quantity, avg_price) VALUES (?, ?, ?, ?)",
            (user_id, ticker, quantity, price),
        )
    db.execute(
        "UPDATE portfolios SET cash_cents = ?, updated_at = ? WHERE user_id = ?",
        (cash - total_cents, now(), user_id),
    )
    db.execute(
        "INSERT INTO transactions (user_id, ticker, type, quantity, price, total_cents, created_at) "
        "VALUES (?, ?, 'BUY', ?, ?, ?, ?)",
        (user_id, ticker, quantity, price, total_cents, now()),
    )
    db.commit()
    return {"ticker": ticker, "quantity": quantity, "price": price, "total": total_cents / 100}


def sell(db, user_id, ticker, quantity=None, sell_all=False):
    ticker = ticker.upper()
    row = db.execute(
        "SELECT * FROM holdings WHERE user_id = ? AND ticker = ?", (user_id, ticker)
    ).fetchone()
    if not row:
        raise TradeError("You do not own any shares of that company.")
    if sell_all:
        quantity = row["quantity"]
    if quantity is None or quantity <= 0:
        raise TradeError("Enter how many shares to sell.")
    quantity = round(quantity, 4)
    if quantity > row["quantity"] + 0.00001:
        raise TradeError("You only own %s shares." % row["quantity"])
    quantity = min(quantity, row["quantity"])
    price = market.price_at(ticker)
    total_cents = int(round(quantity * price * 100))
    left = round(row["quantity"] - quantity, 4)
    if left <= 0.00005:
        db.execute("DELETE FROM holdings WHERE user_id = ? AND ticker = ?", (user_id, ticker))
    else:
        db.execute(
            "UPDATE holdings SET quantity = ? WHERE user_id = ? AND ticker = ?", (left, user_id, ticker)
        )
    cash = get_cash_cents(db, user_id)
    db.execute(
        "UPDATE portfolios SET cash_cents = ?, updated_at = ? WHERE user_id = ?",
        (cash + total_cents, now(), user_id),
    )
    db.execute(
        "INSERT INTO transactions (user_id, ticker, type, quantity, price, total_cents, created_at) "
        "VALUES (?, ?, 'SELL', ?, ?, ?, ?)",
        (user_id, ticker, quantity, price, total_cents, now()),
    )
    db.commit()
    profit = round((price - row["avg_price"]) * quantity, 2)
    return {"ticker": ticker, "quantity": quantity, "price": price, "total": total_cents / 100, "profit": profit}


def reset(db, user_id):
    db.execute("DELETE FROM holdings WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
    db.execute(
        "UPDATE portfolios SET cash_cents = ?, updated_at = ? WHERE user_id = ?",
        (START_CASH_CENTS, now(), user_id),
    )
    db.commit()
