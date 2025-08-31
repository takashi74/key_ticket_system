import os
import logging
import httpx
from fastapi import HTTPException
from urllib.parse import quote

logger = logging.getLogger(__name__)

# 環境変数からPretix設定
PRETIX_CLIENT_ID     = os.getenv("PRETIX_CLIENT_ID")
PRETIX_CLIENT_SECRET = os.getenv("PRETIX_CLIENT_SECRET")
PRETIX_API_TOKEN     = os.getenv("PRETIX_API_TOKEN")
PRETIX_API_BASE      = os.getenv("PRETIX_API_BASE")
PRETIX_ORGANIZER     = os.getenv("PRETIX_ORGANIZER")
REDIRECT_URI         = os.getenv("PRETIX_REDIRECT_URI")

async def get_access_token(client: httpx.AsyncClient, code: str) -> str:
    """OAuth2コードをPretixアクセストークンに交換"""
    try:
        resp = await client.post(
            f"{PRETIX_API_BASE}/{PRETIX_ORGANIZER}/oauth2/v1/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": PRETIX_CLIENT_ID,
                "client_secret": PRETIX_CLIENT_SECRET,
            }
        )
        resp.raise_for_status()
        token_json = resp.json()
        return token_json.get("access_token")
    except Exception as e:
        logger.error(f"Pretix access token error: {e}")
        raise HTTPException(status_code=500, detail="Pretix token error")

async def get_user_info(client: httpx.AsyncClient, access_token: str) -> dict:
    """Pretixからユーザー情報を取得"""
    try:
        resp = await client.get(
            f"{PRETIX_API_BASE}/{PRETIX_ORGANIZER}/oauth2/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Pretix userinfo error: {e}")
        raise HTTPException(status_code=500, detail="Pretix userinfo error")

async def get_orders(client: httpx.AsyncClient, email: str) -> dict:
    """ユーザーの注文情報を取得"""
    try:
        url = f"{PRETIX_API_BASE}/api/v1/organizers/{PRETIX_ORGANIZER}/orders/?email={quote(email)}"
        resp = await client.get(url, headers={"Authorization": f"Token {PRETIX_API_TOKEN}"})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Pretix orders error: {e}")
        raise HTTPException(status_code=500, detail="Pretix orders error")
