"""
SQLAlchemy configuration for NeuroNudge.

Connects to a remote PostgreSQL instance using the DATABASE_URL environment
variable (required in production on Vercel). We avoid SQLite because the
Vercel serverless filesystem is ephemeral — anything written locally is lost
between invocations.

Exports:
    engine       -- SQLAlchemy engine bound to Postgres
    SessionLocal -- factory that yields a scoped DB session per request
    Base         -- declarative base for ORM models
    User         -- user credentials table
    WellnessLog  -- daily wellness metrics table
    get_db()     -- FastAPI dependency yielding a session and closing it
    init_db()    -- creates tables on first cold start
"""

import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, ForeignKey
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# Vercel sets env vars from the project dashboard. Locally you can export
# DATABASE_URL=postgresql://user:pass@host:5432/dbname
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it in Vercel project settings "
        "(Neon, Supabase, Railway, etc. all provide one)."
    )

# Neon/Supabase require SSL; SQLAlchemy respects sslmode=require in the URL
# but we set pool_pre_ping to survive serverless cold starts and idle drops.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=1,          # keep tiny — each serverless invocation is short lived
    max_overflow=2,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------
class User(Base):
    """Registered app user. Passwords are stored as bcrypt hashes only."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    logs = relationship("WellnessLog", back_populates="user", cascade="all, delete-orphan")


class WellnessLog(Base):
    """One daily entry per user: sleep, stress, screen time, activity."""
    __tablename__ = "wellness_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

    sleep_hours = Column(Float, nullable=False)         # 0-24
    stress_level = Column(Integer, nullable=False)      # 1-10
    screen_time_hours = Column(Float, nullable=False)   # 0-24
    activity_minutes = Column(Integer, nullable=False)  # 0-500

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="logs")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_db():
    """FastAPI dependency — yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_initialised = False
def init_db():
    """Create tables on first cold start. Safe to call repeatedly."""
    global _initialised
    if _initialised:
        return
    Base.metadata.create_all(bind=engine)
    _initialised = True
