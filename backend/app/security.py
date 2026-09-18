from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

COOKIE_NAME = "checkin_session"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expiry_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# Allowance for the wall clock stepping backward between issuing a token and
# checking it. PyJWT rejects a token whose `iat` is in the future, and `iat` is
# truncated to the whole second — so a backward clock correction of even a few
# hundred milliseconds, landing just after a second boundary, makes a token
# minted a moment ago "not yet valid". Measured on Docker Desktop for Windows,
# whose VM clock the host corrects: 1 rejection in ~2.1M mint-then-verify
# cycles, which surfaced as users being logged straight back out after
# signing in. 30s absorbs any realistic correction; it also lets an expired
# session live 30s longer, which is immaterial for an 8-hour session.
TOKEN_CLOCK_LEEWAY = timedelta(seconds=30)


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        leeway=TOKEN_CLOCK_LEEWAY,
    )
