import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from config import FRONTEND_DIR, ALLOWED_HOSTS
from database import init_db
from routers import (auth, stocks, portfolio, watchlist, notes, annotations,
                     parental_controls, dashboard)

app = FastAPI(title="MoneySprout", docs_url=None, redoc_url=None, openapi_url=None)

# only answer for moneysprout.renengine.com (the cloudflare tunnel passes that host through)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

init_db()

app.include_router(auth.router)
app.include_router(stocks.router)
app.include_router(portfolio.router)
app.include_router(watchlist.router)
app.include_router(notes.router)
app.include_router(annotations.router)
app.include_router(parental_controls.router)
app.include_router(dashboard.router)


@app.get("/")
def home():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# serve the html/css/js straight from the frontend folder
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
