from fastapi import FastAPI # type: ignore *****Comment to remove unused import warning*****
from fastapi.middleware.cors import CORSMiddleware # type: ignore *******Comment to remove unused import warning*****

app = FastAPI(
    title="Maps Processing API",
    description="API pour traitement et analyse de cartes historiques",
    version="0.1.0"
)

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