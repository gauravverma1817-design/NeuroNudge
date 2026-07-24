"""
NeuroNudge FastAPI backend — Vercel serverless entry point.

Vercel's @vercel/python builder detects the `app` ASGI object automatically,
so no Mangum wrapper is required. All routes are prefixed with /api so the
frontend can call them with relative paths that work identically in local
dev and in production.
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field, conint, confloat
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt, JWTError

from api.database import get_db, init_db, User, WellnessLog
from api.predictive_model import predict as ml_predict

# ---------------------------------------------------------------------------
# App + config
# ---------------------------------------------------------------------------
app = FastAPI(title="NeuroNudge API", version="1.0.0")

# Same-origin in production (Vercel serves both), but permissive CORS makes
# local `vercel dev` and static previews easier.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGO = "HS256"
JWT_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login", auto_error=False)


@app.on_event("startup")
def _startup():
    """Ensure tables exist on cold start."""
    init_db()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: EmailStr


class LogIn(BaseModel):
    sleep_hours: confloat(ge=0,le=24)
    stress_level: conint(ge=1, le=10)
    screen_time_hours: confloat(ge=0, le=24)
    activity_minutes: conint(ge=0, le=500)


class LogOut(BaseModel):
    id: int
    sleep_hours: float
    stress_level: int
    screen_time_hours: float
    activity_minutes: int
    created_at: datetime

    class Config:
        from_attributes = True


class PredictionOut(BaseModel):
    risk_label: int
    risk_probability: float
    risk_level: str
    nudges: list[str]


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def _hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def _verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


def _create_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "neuronudge"}


@app.post("/api/signup", response_model=TokenOut, status_code=201)
def signup(payload: SignupIn, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=payload.email, password_hash=_hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    token = _create_token(user.id, user.email)
    return TokenOut(access_token=token, email=user.email)


@app.post("/api/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not _verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = _create_token(user.id, user.email)
    return TokenOut(access_token=token, email=user.email)


@app.get("/api/me")
def me(current: User = Depends(get_current_user)):
    return {"id": current.id, "email": current.email}


@app.post("/api/logs", response_model=LogOut, status_code=201)
def create_log(
    payload: LogIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    log = WellnessLog(
        user_id=current.id,
        sleep_hours=payload.sleep_hours,
        stress_level=payload.stress_level,
        screen_time_hours=payload.screen_time_hours,
        activity_minutes=payload.activity_minutes,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@app.get("/api/logs", response_model=list[LogOut])
def list_logs(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return (
        db.query(WellnessLog)
        .filter(WellnessLog.user_id == current.id)
        .order_by(WellnessLog.created_at.desc())
        .limit(30)
        .all()
    )


@app.post("/api/predict", response_model=PredictionOut)
def predict_route(
    payload: LogIn,
    current: User = Depends(get_current_user),
):
    """Run the ML model against a single input (does NOT persist the log)."""
    return ml_predict(
        sleep_hours=payload.sleep_hours,
        stress_level=payload.stress_level,
        screen_time_hours=payload.screen_time_hours,
        activity_minutes=payload.activity_minutes,
    )
