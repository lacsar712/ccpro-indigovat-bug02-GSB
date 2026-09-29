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


def _ensure_schema() -> None:
    """create_all 之后为存量库幂等补列：缸容乐观锁版本戳。"""
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if "vats" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("vats")}
        if "lock_version" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE vats ADD COLUMN lock_version INTEGER "
                        "NOT NULL DEFAULT 1"
                    )
                )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_schema()
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
