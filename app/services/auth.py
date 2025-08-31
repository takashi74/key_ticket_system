import os
import time
import jwt
import logging
from fastapi import HTTPException
from typing import Dict, Any

logger = logging.getLogger(__name__)

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_EXP    = int(os.getenv("JWT_EXP", 300))

def create_token(email: str, has_ticket: bool, jstream_tracks: Dict[str, bool]) -> str:
    """JWT を生成"""
    payload = {
        "email": email,
        "has_ticket": has_ticket,
        "jstream_registered_tracks": jstream_tracks,
        "exp": int(time.time()) + JWT_EXP,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    logger.info("JWT generated for %s", email)
    return token

def decode_token(token: str) -> Dict[str, Any]:
    """JWT をデコードして検証"""
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return decoded
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
