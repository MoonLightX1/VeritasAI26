import os
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, PlainTextResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from services.market import MarketUnavailable
import security
from config import FRONTEND_DIR, ALLOWED_HOSTS, COOKIE_SECURE
from database import init_db
from routers.auth import client_ip
from routers import (auth, stocks, portfolio, watchlist, notes, annotations,
                     parental_controls, dashboard)

app = FastAPI(title="MoneySprout", docs_url=None, redoc_url=None, openapi_url=None)

# only answer for moneysprout.renengine.com (the cloudflare tunnel passes that host through)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

init_db()


MAX_BODY = 400_000
OUR_HOSTS = set(h.split(":")[0].lower() for h in ALLOWED_HOSTS)

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


def deny(code, msg):
    return JSONResponse(status_code=code, content={"detail": msg})


# one place for the security checks and headers
@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path

    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        # csrf: a browser tells us where the request came from, it has to be us
        origin = request.headers.get("origin")
        if origin and (urlparse(origin).hostname or "").lower() not in OUR_HOSTS:
            return deny(403, "Blocked.")
        if request.headers.get("sec-fetch-site") == "cross-site":
            return deny(403, "Blocked.")
        # no giant bodies
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY:
            return deny(413, "That is too big.")

    # overall limit per visitor so nobody hammers the api (and our yahoo budget)
    if path.startswith("/api") and security.too_many("api:" + client_ip(request), limit=600, window=60):
        return deny(429, "Slow down a bit.")

    resp = await call_next(request)

    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resp.headers["Content-Security-Policy"] = CSP
    if COOKIE_SECURE:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000"
    if path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-store"
    else:
        # always recheck the html/js/css so old copies do not stick around
        resp.headers["Cache-Control"] = "no-cache"
    return resp


# if the market data provider is down, say so instead of crashing
@app.exception_handler(MarketUnavailable)
def market_down(request: Request, exc: MarketUnavailable):
    return JSONResponse(status_code=503, content={"detail": "Live market data is not available right now. " + str(exc) + " Try again in a minute."})

app.include_router(auth.router)
app.include_router(stocks.router)
app.include_router(portfolio.router)
app.include_router(watchlist.router)
app.include_router(notes.router)
app.include_router(annotations.router)
app.include_router(parental_controls.router)
app.include_router(dashboard.router)


# every page name that has an html file, so /login works without .html
PAGES = set(f[:-5] for f in os.listdir(FRONTEND_DIR) if f.endswith(".html"))


@app.get("/")
def home():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/{page}")
def serve_page(page: str, request: Request):
    # old links with .html just bounce to the clean one
    if page.endswith(".html"):
        name = page[:-5]
        target = "/" if name == "index" else "/" + name
        if request.url.query:
            target += "?" + request.url.query
        return RedirectResponse(target, status_code=307)
    # only names from the list above, so nobody can ask for random files
    if page in PAGES and page != "index":
        return FileResponse(os.path.join(FRONTEND_DIR, page + ".html"))
    return PlainTextResponse("Not found", status_code=404)


# css and js folders are plain static files
app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")
