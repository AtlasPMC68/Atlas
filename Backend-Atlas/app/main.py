from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import celery_router
from .routers import auth
from .routers import dev_test
from .routers import projects
from .routers import user
from .utils.dev_test_assets import GEOREF_ASSETS_DIR, ensure_georef_assets_dir

app = FastAPI(
    title="Maps Processing API",
    description="API pour traitement et analyse de cartes historiques",
    version="0.1.0",
)
app.include_router(celery_router.router)
app.include_router(projects.router)
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(dev_test.router)
# TODO: gate dev_test router and /dev-test static mount behind an ENABLE_DEV_TOOLS env var before any non-local deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve georef dev-test assets (images, GeoJSON, etc.) as static files under /dev-test
ensure_georef_assets_dir()
app.mount("/dev-test", StaticFiles(directory=GEOREF_ASSETS_DIR), name="dev-test")


@app.get("/")
def read_root():
    return {"message": "Maps Processing API", "status": "running"}


@app.get("/ping")
def ping():
    return {"message": "pong"}
