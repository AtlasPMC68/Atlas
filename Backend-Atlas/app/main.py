import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import celery_router
from .routers import auth
from .routers import dev_test
from .routers import imports
from .routers import projects
from .routers import user
from .utils.dev_test_assets import GEOREF_ASSETS_DIR, ensure_georef_assets_dir

# The dev-test tool: its API routes (run, edit and delete test cases) and its
# static files. On by default for now, for local development.
# TODO: default this to "false" before deploying anywhere, so production does
# not expose the dev-test routes; set ENABLE_DEV_TOOLS=true locally instead.
ENABLE_DEV_TOOLS = os.getenv("ENABLE_DEV_TOOLS", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

app = FastAPI(
    title="Maps Processing API",
    description="API pour traitement et analyse de cartes historiques",
    version="0.1.0",
)
app.include_router(celery_router.router)
app.include_router(projects.router)
app.include_router(imports.router)
app.include_router(auth.router)
app.include_router(user.router)
if ENABLE_DEV_TOOLS:
    app.include_router(dev_test.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve georef dev-test assets (images, GeoJSON, etc.) as static files under /dev-test
if ENABLE_DEV_TOOLS:
    ensure_georef_assets_dir()
    app.mount("/dev-test", StaticFiles(directory=GEOREF_ASSETS_DIR), name="dev-test")


@app.get("/")
def read_root():
    return {"message": "Maps Processing API", "status": "running"}


@app.get("/ping")
def ping():
    return {"message": "pong"}
