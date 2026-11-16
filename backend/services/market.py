import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

# prices from yahoo finance, no api key
# unofficial, so it can be slow or change. prices are up to about 15 min late
# everything goes through fetch_chart()

# (the last two numbers in each row are leftovers, not used)
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


# index symbols on yahoo
INDICES = [
    ("SPX", "S&P 500", "^GSPC"),
    ("IXIC", "NASDAQ Composite", "^IXIC"),
    ("DJI", "Dow Jones", "^DJI"),
]

BY_TICKER = {}
for c in COMPANIES:
    BY_TICKER[c[0]] = {
        "ticker": c[0], "name": c[1], "exchange": c[2], "sector": c[3], "industry": c[4],
        "headquarters": c[5], "founded": c[6], "description": c[9],
    }

SOURCE = "Yahoo Finance"

# range name -> (yahoo range, yahoo interval, how long to cache in seconds)
RANGE_MAP = {
    "1D": ("1d", "1m", 20),
    "1W": ("5d", "15m", 60),
    "1M": ("1mo", "1d", 600),
    "3M": ("3mo", "1d", 600),
    "6M": ("6mo", "1d", 600),
    "1Y": ("1y", "1d", 600),
    "5Y": ("5y", "1d", 3600),
    "MAX": ("max", "1wk", 3600),
}

QUOTE_TTL = 20      # seconds, shared by everyone
STALE_OK = 6 * 3600  # if yahoo is down we show an older copy for this long


class MarketUnavailable(Exception):
    pass


_cache = {}          # key -> (time, data)
_locks = {}          # key -> lock
_locks_guard = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=8)


def is_company(ticker):
    return (ticker or "").upper() in BY_TICKER


def _lock_for(key):
    with _locks_guard:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


# two yahoo hostnames, try the other if one fails
HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]

# after a failure, wait a few seconds before asking again
_down_until = 0.0


def fetch_chart(symbol, rng, interval):
    # the only function that talks to yahoo
    global _down_until
    if time.time() < _down_until:
        raise MarketUnavailable("Market data provider is not answering right now.")

    path = "/v8/finance/chart/%s?range=%s&interval=%s&includePrePost=false&events=div%%2Csplit" % (
        urllib.parse.quote(symbol, safe=""), rng, interval)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://finance.yahoo.com/",
    }

    last = "Could not reach the market data provider."
    blocked = False
    for attempt in range(2):
        for host in HOSTS:
            req = urllib.request.Request("https://" + host + path, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=6) as r:
                    data = json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                last = "Market data provider said %s." % e.code
                blocked = e.code in (429, 403) or e.code >= 500
                continue
            except Exception:
                last = "Could not reach the market data provider."
                blocked = True
                continue
            res = (data.get("chart") or {}).get("result")
            if res:
                return res[0]
            last = "No market data came back for %s." % symbol
        time.sleep(0.4)

    if blocked:
        _down_until = time.time() + 8
    raise MarketUnavailable(last)


def _parse(result):
    meta = result.get("meta") or {}
    ts = result.get("timestamp") or []
    q = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = q.get("close") or []
    vols = q.get("volume") or []
    pts = []
    for i, t in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        v = vols[i] if i < len(vols) and vols[i] is not None else 0
        pts.append({"t": int(t) * 1000, "c": round(float(c), 2), "v": int(v)})
    return meta, pts


def _get(symbol, rng_name):
    # cached fetch -> (meta, points, fetched_at, is_stale)
    rng, interval, ttl = RANGE_MAP[rng_name]
    key = (symbol, rng_name)
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1], hit[2], hit[0], False
    with _lock_for(key):
        # may have been filled while we waited
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1], hit[2], hit[0], False
        try:
            meta, pts = _parse(fetch_chart(symbol, rng, interval))
            if not pts:
                raise MarketUnavailable("No price points for %s." % symbol)
            _cache[key] = (time.time(), meta, pts)
            return meta, pts, _cache[key][0], False
        except MarketUnavailable:
            if hit and time.time() - hit[0] < STALE_OK:
                return hit[1], hit[2], hit[0], True
            raise


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"


def _market_open(meta):
    reg = ((meta.get("currentTradingPeriod") or {}).get("regular")) or {}
    try:
        return reg["start"] <= time.time() <= reg["end"]
    except KeyError:
        return False


def _quote_for(symbol, label):
    meta, pts, fetched, stale = _get(symbol, "1D")
    price = meta.get("regularMarketPrice")
    if price is None:
        price = pts[-1]["c"]
    prev = meta.get("chartPreviousClose") or meta.get("previousClose") or pts[0]["c"]
    change = round(price - prev, 2)
    pct = round(change / prev * 100, 2) if prev else 0
    when = meta.get("regularMarketTime") or (pts[-1]["t"] // 1000)
    return {
        "ticker": label,
        "price": round(float(price), 2),
        "previous_close": round(float(prev), 2),
        "change": change,
        "change_pct": pct,
        "as_of": _iso(when),
        "market_open": _market_open(meta),
        "stale": stale,
        "source": SOURCE,
        "note": "Live data from Yahoo Finance. Can be up to about 15 minutes behind.",
    }


def quote(ticker):
    ticker = ticker.upper()
    return _quote_for(ticker, ticker)


def market_status():
    # is the market open, uses apple since it is cached anyway
    try:
        meta = _get("AAPL", "1D")[0]
    except MarketUnavailable:
        return {"known": False, "open": False}
    return {"known": True, "open": _market_open(meta)}


def prefetch(tickers, sparks=False):
    # fill the cache for a bunch of stocks at once
    todo = [t.upper() for t in tickers if is_company(t)]
    list(_pool.map(lambda t: _safe(quote, t), todo))
    if sparks:
        list(_pool.map(lambda t: _safe(spark, t), todo))


def _safe(fn, *a):
    try:
        return fn(*a)
    except MarketUnavailable:
        return None


def history(ticker, rng_name):
    ticker = ticker.upper()
    meta, pts, fetched, stale = _get(ticker, rng_name)
    return {
        "points": pts,
        "stale": stale,
        "fetched_at": _iso(fetched),
        "timezone": meta.get("exchangeTimezoneName") or "America/New_York",
    }


def spark(ticker, n=30):
    try:
        meta, pts, fetched, stale = _get(ticker.upper(), "1M")
    except MarketUnavailable:
        return []
    return [p["c"] for p in pts[-n:]]


def company(ticker):
    info = BY_TICKER.get((ticker or "").upper())
    return dict(info) if info else None


def with_quote(ticker):
    c = company(ticker)
    if not c:
        return None
    c["quote"] = quote(ticker)
    return c


def search(q):
    q = (q or "").strip().lower()
    hits = []
    for c in COMPANIES:
        ticker, name = c[0], c[1]
        if not q or q in ticker.lower() or q in name.lower() or q in c[3].lower() or q in c[4].lower():
            hits.append(ticker)
    prefetch(hits)
    out = []
    for t in hits:
        try:
            out.append(with_quote(t))
        except MarketUnavailable:
            pass
    # exact ticker match first, then ticker prefix
    out.sort(key=lambda x: (x["ticker"].lower() != q, not x["ticker"].lower().startswith(q), x["name"]))
    return out


def index_quotes():
    out = []
    for label, name, symbol in INDICES:
        try:
            qd = _quote_for(symbol, label)
        except MarketUnavailable:
            continue
        qd["name"] = name
        out.append(qd)
    return out


def trending(n=5):
    prefetch([c[0] for c in COMPANIES])
    qs = []
    for c in COMPANIES:
        try:
            qs.append(quote(c[0]))
        except MarketUnavailable:
            pass
    qs.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    top = qs[:n]
    prefetch([q["ticker"] for q in top], sparks=True)
    return [{"ticker": q["ticker"], "name": company(q["ticker"])["name"], "quote": q, "spark": spark(q["ticker"])} for q in top]


def price_at(ticker):
    return quote(ticker)["price"]
