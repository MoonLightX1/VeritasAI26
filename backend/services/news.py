import json
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime

# Company news from two free sources, no api keys:
#   - Yahoo Finance's search feed (financial news)
#   - Google News rss (much wider, and it is how we catch things Yahoo skips, like an
#     executive scandal, a lawsuit or an investigation)
# We run several searches per company at the same time and merge them, so the prediction
# sees a lot more than one feed's top 10. Both feeds are unofficial: if one is down we use
# the other, and if both are down we return [] and the prediction uses the price trend only.

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
YAHOO_HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
NEWS_TTL = 900  # seconds
MAX_ITEMS = 45

_cache = {}
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=8)


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=dict({"User-Agent": UA}, **(headers or {})))
    with urllib.request.urlopen(req, timeout=7) as r:
        return r.read().decode("utf-8", "replace")


def _yahoo(query):
    path = "/v1/finance/search?q=%s&newsCount=25&quotesCount=0&listsCount=0" % urllib.parse.quote(query, safe="")
    for host in YAHOO_HOSTS:
        try:
            data = json.loads(_get("https://" + host + path, {"Referer": "https://finance.yahoo.com/"}))
        except Exception:
            continue
        out = []
        for n in data.get("news") or []:
            out.append({
                "title": (n.get("title") or "").strip(),
                "publisher": n.get("publisher") or "",
                "link": n.get("link") or "",
                "time": int(n.get("providerPublishTime") or 0),
            })
        return out
    return []


def parse_google(xml_text):
    out = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src = (it.findtext("source") or "").strip()
        try:
            t = int(parsedate_to_datetime(it.findtext("pubDate")).timestamp())
        except Exception:
            t = 0
        # google adds " - Publisher" to the end of every title
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3].strip()
        out.append({"title": title, "publisher": src, "link": link, "time": t})
    return out


def _google(query, days):
    q = "%s when:%dd" % (query, days)
    url = "https://news.google.com/rss/search?q=%s&hl=en-US&gl=US&ceid=US:en" % urllib.parse.quote(q)
    try:
        return parse_google(_get(url))
    except Exception:
        return []


def _norm(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()[:70]


def _plain_name(name):
    # "Alphabet (Google)" -> ("Alphabet", "Google")
    base = re.sub(r"\s*\(.*?\)", "", name).strip()
    m = re.search(r"\((.*?)\)", name)
    return base, (m.group(1) if m else "")


def headlines(ticker, name=None):
    """Recent news for a company: [{title, publisher, link, time}], newest first (up to 45).
    Returns [] if every source is down."""
    ticker = ticker.upper()
    now = time.time()
    hit = _cache.get(ticker)
    if hit and now - hit[0] < NEWS_TTL:
        return hit[1]

    with _lock:
        hit = _cache.get(ticker)
        if hit and time.time() - hit[0] < NEWS_TTL:
            return hit[1]

        base, alt = _plain_name(name or ticker)
        who = base or ticker
        jobs = [
            (_yahoo, (ticker,)),
            (_yahoo, (who,)),
            (_google, ("%s stock" % who, 14)),
            (_google, ("%s earnings OR analyst OR forecast" % who, 14)),
            (_google, ("%s CEO OR chairman OR executive OR founder" % who, 21)),
            # the stuff that moves a stock and never shows up in a "stock news" feed
            (_google, ("%s scandal OR affair OR lawsuit OR investigation OR allegations OR resigns OR fraud" % who, 30)),
            (_google, ("%s regulators OR ban OR tariffs OR export OR antitrust" % who, 21)),
        ]
        futures = [_pool.submit(fn, *args) for fn, args in jobs]
        raw = []
        for i, f in enumerate(futures):
            try:
                got = f.result(timeout=15)
            except Exception:
                continue
            for n in got:
                # yahoo's own ticker feed is already about this company
                n["trusted"] = (i == 0)
            raw.extend(got)

        if not raw:
            # keep serving an old copy rather than nothing
            return hit[1] if hit else []

        # google searches can drift off topic, so those must mention the company
        keys = [k.lower() for k in (ticker, who, alt) if k and len(k) > 2]
        out, seen = [], set()
        for n in raw:
            title, link = n["title"], n["link"]
            if not title or not link.startswith("https://"):
                continue
            norm = _norm(title)
            if norm in seen:
                continue
            if not n.get("trusted") and not any(k in title.lower() for k in keys):
                continue
            seen.add(norm)
            n.pop("trusted", None)
            if not n["time"]:
                n["time"] = int(now)
            out.append(n)
        out.sort(key=lambda x: x["time"], reverse=True)
        out = out[:MAX_ITEMS]
        _cache[ticker] = (time.time(), out)
        return out
