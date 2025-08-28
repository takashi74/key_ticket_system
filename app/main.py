import logging
import os
import time
from contextlib import asynccontextmanager
from urllib.parse import quote
import jwt
import httpx
from fastapi import FastAPI, Request, Query, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# --------------------------
# ログ設定
# --------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------------
# 環境変数読み込み
# --------------------------
load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
TOKEN_URL = os.getenv("TOKEN_URL")
PRETIX_API_BASE = os.getenv("PRETIX_API_BASE")
PRETIX_API_TOKEN = os.getenv("PRETIX_API_TOKEN")
ORGANIZER = os.getenv("ORGANIZER")
LIVE_TICKET_ID = int(os.getenv("LIVE_TICKET_ID"))
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_EXP = int(os.getenv("JWT_EXP"))
STATIC_PAGE_URL = os.getenv("STATIC_PAGE_URL")
ALLOWED_ORIGINS_STR = os.getenv("ALLOWED_ORIGINS")
ALLOWED_METHODS_STR = os.getenv("ALLOWED_METHODS", "*")
ALLOWED_HEADERS_STR = os.getenv("ALLOWED_HEADERS", "*")

# 必須の環境変数のチェック
REQUIRED_ENV = [
    "CLIENT_ID", "CLIENT_SECRET", "REDIRECT_URI", "TOKEN_URL", "PRETIX_API_TOKEN",
    "PRETIX_API_BASE", "ORGANIZER", "LIVE_TICKET_ID", "JWT_SECRET", "JWT_EXP",
    "STATIC_PAGE_URL", "ALLOWED_ORIGINS"
]
for var in REQUIRED_ENV:
    if not os.getenv(var):
        raise ValueError(f"Missing required environment variable: {var}")

# --------------------------
# FastAPI 初期化
# --------------------------
# asynccontextmanager を使用して、アプリケーションのライフサイクル内で httpx クライアントを管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.httpx_client = httpx.AsyncClient()
    logger.info("HTTPX client started.")
    yield
    await app.state.httpx_client.aclose()
    logger.info("HTTPX client closed.")

app = FastAPI(lifespan=lifespan)

# CORS設定
origins = ALLOWED_ORIGINS_STR.split(',') if ALLOWED_ORIGINS_STR else []
methods = ALLOWED_METHODS_STR.split(',') if ALLOWED_METHODS_STR else ["*"]
headers = ALLOWED_HEADERS_STR.split(',') if ALLOWED_HEADERS_STR else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=methods,
    allow_headers=headers,
)

# 依存関係として httpx クライアントを提供
def get_httpx_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.httpx_client

# --------------------------
# OAuth2 コールバック
# --------------------------
@app.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(..., description="OAuth2 authorization code"),
    client: httpx.AsyncClient = Depends(get_httpx_client)
):
    logger.info(f"Received OAuth2 code: {code}")

    # 1. アクセストークン取得
    try:
        token_resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            }
        )
        token_resp.raise_for_status()
        token_json = token_resp.json()
        access_token = token_json.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to get access token from token endpoint.")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during token exchange: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to exchange code for token: {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Request error during token exchange: {e}")
        raise HTTPException(status_code=500, detail="Network error during token exchange.")

    # 2. Pretix APIでユーザー情報取得
    try:
        user_resp = await client.get(
            f"{PRETIX_API_BASE}/{ORGANIZER}/oauth2/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        user_resp.raise_for_status()
        user_info = user_resp.json()
        email = user_info.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Email not found in user info.")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during userinfo fetch: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to fetch user info: {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Request error during userinfo fetch: {e}")
        raise HTTPException(status_code=500, detail="Network error during user info fetch.")

    # 3. Pretix APIで購入情報取得
    try:
        orders_url = f"{PRETIX_API_BASE}/api/v1/organizers/{ORGANIZER}/orders/?email={quote(email)}"
        headers = {"Authorization": f"Token {PRETIX_API_TOKEN}"}
        orders_resp = await client.get(orders_url, headers=headers)
        orders_resp.raise_for_status()
        orders_data = orders_resp.json()

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during orders fetch: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to fetch orders: {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Request error during orders fetch: {e}")
        raise HTTPException(status_code=500, detail="Network error during orders fetch.")

    has_ticket = any(
        pos.get("item") == LIVE_TICKET_ID
        for order in orders_data.get("results", [])
        for pos in order.get("positions", [])
    )
    logger.info(f"User '{email}' has_ticket: {has_ticket}")

    # 4. JWT生成（email + has_ticket）
    payload = {
        "email": email,
        "has_ticket": has_ticket,
        "exp": int(time.time()) + JWT_EXP
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    logger.info(f"Generated JWT: {token}")

    # 5. 静的ページにリダイレクト
    redirect_url = f"{STATIC_PAGE_URL}?token={quote(token)}"
    logger.info(f"Redirect URL: {redirect_url}")
    return RedirectResponse(url=redirect_url)

# --------------------------
# JWT検証API
# --------------------------
@app.get("/verify")
async def verify(token: str = Query(...)):
    logger.info(f"Received token for verification: {token}")
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        logger.info(f"Decoded payload: {decoded}")
        return {
            "email": decoded["email"],
            "has_ticket": decoded["has_ticket"]
        }
    except jwt.ExpiredSignatureError:
        logger.warning("JWT expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
