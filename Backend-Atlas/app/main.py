import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import celery_router
from .routers import auth
from .routers import maps
from .routers import user

app = FastAPI(
    title="Maps Processing API",
    description="API pour traitement et analyse de cartes historiques",
    version="0.1.0",
)
app.include_router(celery_router.router)
app.include_router(maps.router)
app.include_router(auth.router)
app.include_router(user.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve test assets (images, GeoJSON, etc.) as static files under /dev-test
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
TEST_ASSETS_DIR = os.path.join(ROOT_DIR, "tests", "assets")

if os.path.isdir(TEST_ASSETS_DIR):
    app.mount("/dev-test", StaticFiles(directory=TEST_ASSETS_DIR), name="dev-test")


@app.get("/")
def read_root():
    return {"message": "Maps Processing API", "status": "running"}


@app.get("/ping")
def ping():
    return {"message": "pong"}
