import logging
import os
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, PlainTextResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from services.market import MarketUnavailable
import security
from config import FRONTEND_DIR, ALLOWED_HOSTS, COOKIE_SECURE, PUBLIC_HOST
from database import init_db
from routers.auth import client_ip
from routers import (auth, stocks, portfolio, watchlist, notes, annotations,
                     parental_controls, dashboard)

app = FastAPI(title="MoneySprout", docs_url=None, redoc_url=None, openapi_url=None)

# only answer to our own hostname
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

init_db()


MAX_BODY = 400_000
OUR_HOSTS = set(h.split(":")[0].lower() for h in ALLOWED_HOSTS)
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")

# no CORS on purpose, the site only talks to itself

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
       "frame-ancestors 'none'")
if COOKIE_SECURE:
    CSP += "; upgrade-insecure-requests"


def deny(code, msg):
    return JSONResponse(status_code=code, content={"detail": msg})


# security checks and headers all live here
@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    is_api = path.startswith("/api")

    # http -> https
    if COOKIE_SECURE:
        proto = request.headers.get("x-forwarded-proto", "").lower()
        visitor = request.headers.get("cf-visitor", "")
        if proto == "http" or '"scheme":"http"' in visitor.replace(" ", ""):
            target = "https://" + PUBLIC_HOST + path
            if request.url.query:
                target += "?" + request.url.query
            return RedirectResponse(target, status_code=308)

    if request.method in WRITE_METHODS:
        # csrf check, the request has to come from us
        origin = request.headers.get("origin")
        if origin and (urlparse(origin).hostname or "").lower() not in OUR_HOSTS:
            logging.getLogger("moneysprout").warning("blocked: origin %s", origin[:100])
            return deny(403, "Blocked: this request came from another site.")
        if request.headers.get("sec-fetch-site") == "cross-site":
            logging.getLogger("moneysprout").warning("blocked: cross-site request")
            return deny(403, "Blocked: this request came from another site.")
        if is_api:
            # other sites cannot add this header
            if request.headers.get("x-requested-with") != "moneysprout":
                # usually an old cached app.js
                logging.getLogger("moneysprout").warning("blocked: missing x-requested-with on %s", path)
                return deny(403, "Blocked: your browser is running an old copy of the site. Hard refresh with Ctrl+Shift+R.")
            cl = request.headers.get("content-length")
            ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
            if cl and cl != "0" and ctype != "application/json":
                return deny(415, "Send json.")
        # no huge bodies
        if request.headers.get("transfer-encoding"):
            return deny(411, "Send a content length.")
        cl = request.headers.get("content-length")
        if cl and (not cl.isdigit() or int(cl) > MAX_BODY):
            return deny(413, "That is too big.")

    # rate limit per visitor
    if is_api:
        ip = client_ip(request)
        if security.too_many("api:" + ip, limit=600, window=60):
            return deny(429, "Slow down a bit.")
        # writes get a smaller limit
        if request.method in WRITE_METHODS and security.too_many("write:" + ip, limit=150, window=60):
            return deny(429, "Slow down a bit.")

    resp = await call_next(request)

    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resp.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    resp.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    resp.headers["Content-Security-Policy"] = CSP
    if COOKIE_SECURE:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000"
    if is_api:
        resp.headers["Cache-Control"] = "no-store"
    else:
        # no caching, so an old app.js never runs against a new backend
        resp.headers["Cache-Control"] = "no-store"
    return resp


# yahoo down, say so instead of crashing
@app.exception_handler(MarketUnavailable)
def market_down(request: Request, exc: MarketUnavailable):
    return JSONResponse(status_code=503, content={"detail": "Live market data is not available right now. " + str(exc) + " Try again in a minute."})

# bad input: say what is wrong, never echo it back (like a password)
@app.exception_handler(RequestValidationError)
def bad_input(request: Request, exc: RequestValidationError):
    errs = exc.errors()
    msg = str(errs[0].get("msg", "That does not look right.")) if errs else "That does not look right."
    if msg.startswith("Value error, "):
        msg = msg[len("Value error, "):]
    return JSONResponse(status_code=422, content={"detail": [{"msg": msg}]})


# anything unexpected gets logged, user just sees a generic error
@app.exception_handler(Exception)
def oops(request: Request, exc: Exception):
    logging.getLogger("moneysprout").exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side."})


app.include_router(auth.router)
app.include_router(stocks.router)
app.include_router(portfolio.router)
app.include_router(watchlist.router)
app.include_router(notes.router)
app.include_router(annotations.router)
app.include_router(parental_controls.router)
app.include_router(dashboard.router)


# so /login works without .html
PAGES = set(f[:-5] for f in os.listdir(FRONTEND_DIR) if f.endswith(".html"))


@app.get("/")
def home():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/{page}")
def serve_page(page: str, request: Request):
    # .html links redirect to the clean url
    if page.endswith(".html"):
        name = page[:-5]
        target = "/" if name == "index" else "/" + name
        if request.url.query:
            target += "?" + request.url.query
        return RedirectResponse(target, status_code=307)
    # only names from the list, no random files
    if page in PAGES and page != "index":
        return FileResponse(os.path.join(FRONTEND_DIR, page + ".html"))
    return PlainTextResponse("Not found", status_code=404)


# static folders
app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")
app.mount("/fonts", StaticFiles(directory=os.path.join(FRONTEND_DIR, "fonts")), name="fonts")
app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")
