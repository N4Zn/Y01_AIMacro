"""Băm mật khẩu (pbkdf2, không phụ thuộc thư viện C ngoài) + JWT access token + refresh token ngẫu nhiên."""
import hashlib
import hmac
import secrets
import time

import jwt

from . import config

PBKDF2_ITERATIONS = 200_000


def hash_password(password: str):
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return salt, h.hex()


def verify_password(password: str, salt: str, hash_hex: str) -> bool:
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return hmac.compare_digest(h.hex(), hash_hex)


def create_access_token(user_id: str, plan: str) -> str:
    payload = {"sub": user_id, "plan": plan, "exp": time.time() + config.ACCESS_TOKEN_MINUTES * 60}
    return jwt.encode(payload, config.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
