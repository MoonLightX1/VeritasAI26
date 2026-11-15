import os
import time
import urllib.parse
import urllib.request

from config import BASE_DIR

# Company logos. The browser can only load images from this site (see the CSP in main.py),
# so the server grabs each logo once, saves it in logo_cache, and serves it from there.
# The domains are a fixed list on purpose, nobody can make the server fetch random sites.

CACHE_DIR = os.path.join(BASE_DIR, "logo_cache")

DOMAINS = {
    "AAPL": "apple.com", "MSFT": "microsoft.com", "NVDA": "nvidia.com", "AMZN": "amazon.com",
    "GOOGL": "google.com", "TSLA": "tesla.com", "META": "meta.com", "NFLX": "netflix.com",
    "DIS": "disney.com", "NKE": "nike.com", "KO": "coca-cola.com", "MCD": "mcdonalds.com",
    "WMT": "walmart.com", "SBUX": "starbucks.com", "COST": "costco.com", "INTC": "intel.com",
    "AMD": "amd.com", "SPOT": "spotify.com", "RBLX": "roblox.com", "F": "ford.com",
}

# tried in order, first one that gives a real image wins
SOURCES = [
    "https://www.google.com/s2/favicons?domain=%s&sz=128",
    "https://icons.duckduckgo.com/ip3/%s.ico",
]

_failed = {}  # ticker -> when we can try again, so a dead provider does not get hammered
RETRY_AFTER = 600


def _kind(data):
    # only trust real image bytes
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"\x00\x00\x01\x00":
        return "image/x-icon"
    return None


def _download(domain):
    for src in SOURCES:
        req = urllib.request.Request(src % urllib.parse.quote(domain, safe=""),
                                     headers={"User-Agent": "Mozilla/5.0 MoneySprout"})
        try:
            with urllib.request.urlopen(req, timeout=6) as r:
                data = r.read(300000)
        except Exception:
            continue
        if len(data) > 200 and _kind(data):
            return data
    return None


def get_logo(ticker):
    # returns (bytes, content_type) or None
    ticker = (ticker or "").upper()
    domain = DOMAINS.get(ticker)
    if not domain:
        return None
    path = os.path.join(CACHE_DIR, ticker + ".img")
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
        return data, _kind(data) or "image/png"
    if time.time() < _failed.get(ticker, 0):
        return None
    data = _download(domain)
    if not data:
        _failed[ticker] = time.time() + RETRY_AFTER
        return None
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return data, _kind(data)
