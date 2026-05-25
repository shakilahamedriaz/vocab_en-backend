from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import engine, Base
from app.api import auth, vocabulary, srs, learning, games

settings = get_settings()

# Create tables
Base.metadata.create_all(bind=engine)

# Add ai_explanation column for SQLite (existing DBs only)
from sqlalchemy import text
if settings.DATABASE_URL.startswith("sqlite"):
    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(vocabulary)"))]
        if "ai_explanation" not in cols:
            conn.execute(text("ALTER TABLE vocabulary ADD COLUMN ai_explanation JSON"))
            conn.commit()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(vocabulary.router, prefix="/api/v1")
app.include_router(srs.router, prefix="/api/v1")
app.include_router(learning.router, prefix="/api/v1")
app.include_router(games.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
