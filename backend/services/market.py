import bisect
import calendar
import hashlib
import math
import random
import datetime as dt

# All prices here are SIMULATED demo data. They are not real market prices.
# Same ticker always gives the same history (seeded), so the demo is stable.

COMPANIES = [
    ("AAPL", "Apple", "NASDAQ", "Technology", "Consumer Electronics", "Cupertino, California", 1976, 210.0, 0.017,
     "Makes the iPhone, Mac computers, iPad and Apple Watch, and sells apps and services."),
    ("MSFT", "Microsoft", "NASDAQ", "Technology", "Software", "Redmond, Washington", 1975, 420.0, 0.015,
     "Makes Windows, Office, Xbox and cloud computing services."),
    ("NVDA", "NVIDIA", "NASDAQ", "Technology", "Semiconductors", "Santa Clara, California", 1993, 130.0, 0.030,
     "Designs graphics chips used in games, data centers and artificial intelligence."),
    ("AMZN", "Amazon", "NASDAQ", "Consumer", "E-commerce and Cloud", "Seattle, Washington", 1994, 185.0, 0.020,
     "Runs an online store, Prime, and the AWS cloud computing business."),
    ("GOOGL", "Alphabet (Google)", "NASDAQ", "Technology", "Internet Services", "Mountain View, California", 1998, 175.0, 0.018,
     "Parent company of Google, YouTube and Android."),
    ("TSLA", "Tesla", "NASDAQ", "Automotive", "Electric Vehicles", "Austin, Texas", 2003, 250.0, 0.036,
     "Builds electric cars and battery energy storage products."),
    ("META", "Meta Platforms", "NASDAQ", "Technology", "Social Media", "Menlo Park, California", 2004, 520.0, 0.023,
     "Owns Facebook, Instagram and WhatsApp."),
    ("NFLX", "Netflix", "NASDAQ", "Entertainment", "Streaming", "Los Gatos, California", 1997, 650.0, 0.022,
     "Streaming service for movies and TV shows."),
    ("DIS", "Walt Disney", "NYSE", "Entertainment", "Media and Parks", "Burbank, California", 1923, 105.0, 0.017,
     "Movies, theme parks, Disney+ and ESPN."),
    ("NKE", "Nike", "NYSE", "Consumer", "Apparel and Shoes", "Beaverton, Oregon", 1964, 90.0, 0.018,
     "Sells athletic shoes, clothing and gear."),
    ("KO", "Coca-Cola", "NYSE", "Consumer", "Beverages", "Atlanta, Georgia", 1892, 62.0, 0.009,
     "Makes and sells Coca-Cola and many other drinks around the world."),
    ("MCD", "McDonald's", "NYSE", "Consumer", "Restaurants", "Chicago, Illinois", 1955, 290.0, 0.011,
     "Fast food restaurant chain with locations in over 100 countries."),
    ("WMT", "Walmart", "NYSE", "Consumer", "Retail", "Bentonville, Arkansas", 1962, 70.0, 0.010,
     "One of the biggest retailers in the world, with stores and online shopping."),
    ("SBUX", "Starbucks", "NASDAQ", "Consumer", "Coffee Shops", "Seattle, Washington", 1971, 95.0, 0.017,
     "Coffee shop chain with thousands of stores worldwide."),
    ("COST", "Costco", "NASDAQ", "Consumer", "Warehouse Retail", "Issaquah, Washington", 1983, 880.0, 0.012,
     "Membership warehouse stores that sell goods in bulk."),
    ("INTC", "Intel", "NASDAQ", "Technology", "Semiconductors", "Santa Clara, California", 1968, 24.0, 0.024,
     "Makes computer processors and other chips."),
    ("AMD", "AMD", "NASDAQ", "Technology", "Semiconductors", "Santa Clara, California", 1969, 155.0, 0.028,
     "Makes processors and graphics chips for PCs, consoles and servers."),
    ("SPOT", "Spotify", "NYSE", "Entertainment", "Music Streaming", "Stockholm, Sweden", 2006, 330.0, 0.026,
     "Music and podcast streaming service."),
    ("RBLX", "Roblox", "NYSE", "Entertainment", "Gaming", "San Mateo, California", 2004, 45.0, 0.030,
     "Online platform where people play and create games made by other users."),
    ("F", "Ford", "NYSE", "Automotive", "Automakers", "Dearborn, Michigan", 1903, 12.0, 0.019,
     "Builds cars, trucks and SUVs, including the F-150 and Mustang."),
]

# fake index levels, also simulated
INDICES = [
    ("SPX", "S&P 500 (demo)", 5900.0, 0.008),
    ("IXIC", "NASDAQ Composite (demo)", 19000.0, 0.011),
    ("DJI", "Dow Jones (demo)", 43000.0, 0.007),
]

START_DATE = dt.date(2016, 1, 4)
ANCHOR_DATE = dt.date(2026, 1, 2)

BY_TICKER = {}
for c in COMPANIES:
    BY_TICKER[c[0]] = {
        "ticker": c[0], "name": c[1], "exchange": c[2], "sector": c[3], "industry": c[4],
        "headquarters": c[5], "founded": c[6], "base": c[7], "vol": c[8], "description": c[9],
    }
for i in INDICES:
    BY_TICKER[i[0]] = {"ticker": i[0], "name": i[1], "base": i[2], "vol": i[3], "index": True}

_cache = {}


def is_company(ticker):
    t = BY_TICKER.get(ticker.upper())
    return bool(t) and not t.get("index")


def _seed(text):
    return int(hashlib.sha256(text.encode()).hexdigest()[:12], 16)


def _weekdays(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def daily(ticker):
    # build the whole daily series, cached per ticker per day
    ticker = ticker.upper()
    today = dt.date.today()
    key = (ticker, today)
    if key in _cache:
        return _cache[key]
    info = BY_TICKER[ticker]
    rng = random.Random(_seed(ticker))
    vol = info["vol"]
    price = 100.0
    raw = []
    regime = 1.0
    for i, d in enumerate(_weekdays(START_DATE, today)):
        # volatility changes slowly so charts look less boring
        if i % 40 == 0:
            regime = rng.uniform(0.6, 1.6)
        ret = 0.0004 + vol * regime * rng.gauss(0, 1)
        price *= math.exp(ret)
        volume = int(info["base"] * 0 + 5_000_000 * rng.uniform(0.6, 1.5) * (1 + abs(ret) * 25))
        raw.append((d, price, volume))
    # scale so price on the anchor date matches the base price (keeps old prices stable)
    anchor_raw = next((p for d, p, v in raw if d >= ANCHOR_DATE), raw[-1][1])
    scale = info["base"] / anchor_raw
    out = []
    for d, p, v in raw:
        t = calendar.timegm(dt.datetime(d.year, d.month, d.day, 20, 0).timetuple()) * 1000
        out.append({"t": t, "c": round(p * scale, 2), "v": v})
    # drop old cache entries
    for k in [k for k in _cache if k[0] == ticker and k != key]:
        del _cache[k]
    _cache[key] = out
    return out


def _intraday(ticker, day_index, bars, step_minutes):
    # walks from the previous close to this day's close with a bridge
    series = daily(ticker)
    prev = series[day_index - 1]["c"]
    close = series[day_index]["c"]
    total_volume = series[day_index]["v"]
    day_ms = series[day_index]["t"]
    d = dt.datetime.utcfromtimestamp(day_ms / 1000)
    start = calendar.timegm(dt.datetime(d.year, d.month, d.day, 9, 30).timetuple()) * 1000
    rng = random.Random(_seed("%s-%d" % (ticker, day_ms)))
    vol = BY_TICKER[ticker]["vol"] / math.sqrt(bars) * 0.8
    walk = [0.0]
    for _ in range(bars):
        walk.append(walk[-1] + rng.gauss(0, vol))
    out = []
    for i in range(1, bars + 1):
        frac = i / bars
        # bridge so the last bar lands on the real close
        bridged = walk[i] - frac * walk[bars]
        price = (prev + (close - prev) * frac) * math.exp(bridged)
        if i == bars:
            price = close
        out.append({
            "t": start + (i - 1) * step_minutes * 60000,
            "c": round(price, 2),
            "v": int(total_volume / bars * rng.uniform(0.5, 1.6)),
        })
    return out


def history(ticker, rng_name):
    ticker = ticker.upper()
    series = daily(ticker)
    n = len(series)
    if rng_name == "1D":
        return _intraday(ticker, n - 1, 78, 5)
    if rng_name == "1W":
        pts = []
        for k in range(5, 0, -1):
            pts += _intraday(ticker, n - k, 13, 30)
        return pts
    counts = {"1M": 22, "3M": 66, "6M": 132, "1Y": 252, "5Y": 1260}
    if rng_name == "MAX":
        return series
    return series[-counts.get(rng_name, 252):]


def quote(ticker):
    ticker = ticker.upper()
    s = daily(ticker)
    last, prev = s[-1], s[-2]
    change = round(last["c"] - prev["c"], 2)
    pct = round(change / prev["c"] * 100, 2) if prev["c"] else 0
    d = dt.datetime.utcfromtimestamp(last["t"] / 1000).date().isoformat()
    return {
        "ticker": ticker,
        "price": last["c"],
        "previous_close": prev["c"],
        "change": change,
        "change_pct": pct,
        "as_of": d,
        "source": "demo",
        "note": "Simulated demo data, not a real market price.",
    }


def spark(ticker, n=30):
    return [p["c"] for p in daily(ticker)[-n:]]


def company(ticker):
    info = BY_TICKER.get(ticker.upper())
    if not info or info.get("index"):
        return None
    return {k: v for k, v in info.items() if k not in ("base", "vol")}


def with_quote(ticker):
    c = company(ticker)
    if not c:
        return None
    c = dict(c)
    c["quote"] = quote(ticker)
    return c


def search(q):
    q = (q or "").strip().lower()
    out = []
    for c in COMPANIES:
        ticker, name = c[0], c[1]
        if not q or q in ticker.lower() or q in name.lower() or q in c[3].lower() or q in c[4].lower():
            out.append(with_quote(ticker))
    # exact ticker match first, then ticker prefix
    out.sort(key=lambda x: (x["ticker"].lower() != q, not x["ticker"].lower().startswith(q), x["name"]))
    return out


def index_quotes():
    out = []
    for t, name, _, _ in INDICES:
        qd = quote(t)
        qd["name"] = name
        out.append(qd)
    return out


def trending(n=5):
    qs = [quote(c[0]) for c in COMPANIES]
    qs.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    out = []
    for qd in qs[:n]:
        c = company(qd["ticker"])
        out.append({"ticker": qd["ticker"], "name": c["name"], "quote": qd})
    return out


def price_at(ticker):
    return quote(ticker)["price"]
