from fastapi import FastAPI # type: ignore *****Comment to remove unused import warning*****
from fastapi.middleware.cors import CORSMiddleware # type: ignore *******Comment to remove unused import warning*****
from app.db import get_db_connection
from .routers import celery_router  # ou le nom de ton router
from .routers import maps  # Ajoutez cette ligne



app = FastAPI(
    title="Maps Processing API",
    description="API pour traitement et analyse de cartes historiques",
    version="0.1.0"
)
app.include_router(celery_router.router)
app.include_router(maps.router)  # Ajoutez cette ligne

# CORS pour frontend local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Maps Processing API", "status": "running"}

@app.get("/ping")
def ping():
    return {"message": "pong"}

@app.get("/db-test")
def db_test():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1;")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return {"db_status": "connected", "result": result}
    except Exception as e:
        return {"db_status": "error", "error": str(e)}