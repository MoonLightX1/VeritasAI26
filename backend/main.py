import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import FRONTEND_DIR
from database import init_db
from routers import (auth, stocks, portfolio, watchlist, notes, annotations,
                     parental_controls, dashboard)

app = FastAPI(title="MoneySprout")

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
