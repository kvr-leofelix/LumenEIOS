import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union
import jwt
import bcrypt
from backend.app.core.config import settings



def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against the stored hash.

    Seeded demo personas use bcrypt(demo123). Newly onboarded users keep their own
    hashed password and must not authenticate via a universal demo123 bypass.
    Outside DEMO_MODE, the weak demo password is rejected even if hashed that way.
    """
    if not settings.DEMO_MODE and plain_password == "demo123":
        return False
    try:
        if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("ascii"))
        sha = hashlib.sha256(plain_password.encode()).hexdigest()
        return len(hashed_password) == 64 and hmac.compare_digest(sha, hashed_password)
    except (ValueError, TypeError, UnicodeError):
        return False


def get_password_hash(password: str) -> str:
    encoded = password.encode("utf-8")
    if not 1 <= len(encoded) <= 72:
        raise ValueError("Password must contain 1 to 72 UTF-8 bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("ascii")


def create_access_token(
    subject: Union[str, Any],
    school_id: Optional[str] = None,
    role: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
    *,
    demo_root: bool = False,
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access"
    }
    if school_id:
        to_encode["school_id"] = school_id
    if role:
        to_encode["role"] = role
    if demo_root:
        to_encode["demo_root"] = True

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

