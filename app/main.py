import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from starlette.middleware.sessions import SessionMiddleware

from app.db import Base, SessionLocal, engine
from app.routers import auth, pages
from app.seed import ensure_seed_data


def _ensure_vat_version_column() -> None:
    """对老库幂等补列：create_all 不会 ALTER 已有表，需手动加乐观锁版本戳。"""
    inspector = inspect(engine)
    if "vats" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("vats")}
    if "version_id" in columns:
        return
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE vats ADD COLUMN version_id INTEGER NOT NULL DEFAULT 0")
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_vat_version_column()
    db = SessionLocal()
    try:
        ensure_seed_data(db)
    finally:
        db.close()
    yield


app = FastAPI(title="IndigoVat 染缸还原台", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "dev-indigovat-session-secret"),
    session_cookie="indigovat_session",
    same_site="lax",
    https_only=False,
)

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(auth.router)
app.include_router(pages.router)
