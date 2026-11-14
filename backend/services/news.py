import json
import threading
import time
import urllib.parse
import urllib.request

# Company news from Yahoo Finance's public search feed. Same provider as the prices,
# so there is no api key to set up. It is unofficial, so if it fails we just return
# no news and the prediction falls back to the price trend alone.

HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
NEWS_TTL = 600  # seconds, news does not change fast and we do not want to hammer yahoo

_cache = {}
_lock = threading.Lock()


def _fetch(query):
    path = "/v1/finance/search?q=%s&newsCount=12&quotesCount=0&listsCount=0" % urllib.parse.quote(query, safe="")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://finance.yahoo.com/",
    }
    for host in HOSTS:
        req = urllib.request.Request("https://" + host + path, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=6) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            continue
    return None


def headlines(ticker):
    """Recent news for a ticker: [{title, publisher, link, time (unix seconds)}], newest first.
    Returns [] if the provider is down."""
    ticker = ticker.upper()
    now = time.time()
    hit = _cache.get(ticker)
    if hit and now - hit[0] < NEWS_TTL:
        return hit[1]

    with _lock:
        hit = _cache.get(ticker)
        if hit and time.time() - hit[0] < NEWS_TTL:
            return hit[1]
        data = _fetch(ticker)
        if data is None:
            # keep serving an old copy rather than nothing
            return hit[1] if hit else []
        out = []
        seen = set()
        for n in data.get("news") or []:
            title = (n.get("title") or "").strip()
            link = n.get("link") or ""
            if not title or title.lower() in seen or not link.startswith("https://"):
                continue
            seen.add(title.lower())
            out.append({
                "title": title,
                "publisher": n.get("publisher") or "",
                "link": link,
                "time": int(n.get("providerPublishTime") or now),
            })
        out.sort(key=lambda x: x["time"], reverse=True)
        _cache[ticker] = (time.time(), out)
        return out
