from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.routes import auth, claims, clue_reviews, dashboard, document_triage, model
from src.utils.db import get_conn

@asynccontextmanager
async def lifespan(app):
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    with get_conn() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(1045002)")
        for name in ("002_clue_reviews.sql", "003_document_followups.sql"):
            conn.execute((migrations / name).read_text(encoding="utf-8"))
    yield


app = FastAPI(title="Claim Lead Classification API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router)
app.include_router(claims.router)
app.include_router(clue_reviews.router)
app.include_router(document_triage.router)
app.include_router(dashboard.router)
app.include_router(model.router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "backend"}
