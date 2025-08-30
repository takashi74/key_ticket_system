import logging
import os
import time
from contextlib import asynccontextmanager
from urllib.parse import quote

import httpx
import jwt
import tomli
from fastapi import FastAPI, Request, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from pathlib import Path

# --------------------------
# ログ設定
# --------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------------
# 設定ファイル読み込み
# --------------------------
def load_config(file_path: Path):
    """TOML設定ファイルを読み込む"""
    try:
        with open(file_path, "rb") as f:
            return tomli.load(f)
    except FileNotFoundError:
        logger.error(f"Config file not found: {file_path}")
        raise
    except tomli.TOMLDecodeError:
        logger.error(f"Failed to parse TOML file: {file_path}")
        raise

# --------------------------
# 環境変数 設定 読み込み
# --------------------------
# gunicornのWorkingDirectoryを基準にconfig.tomlを読み込む
# systemdユニットファイルでEnvironmentFileが設定されているため、
# os.getenv()は直接環境変数を読み込めます。
config_path = Path(os.environ.get("CONFIG_PATH", "config.toml"))
config = load_config(config_path)

PRETIX_CLIENT_ID        = os.getenv("PRETIX_CLIENT_ID")
PRETIX_CLIENT_SECRET    = os.getenv("PRETIX_CLIENT_SECRET")
PRETIX_API_TOKEN        = os.getenv("PRETIX_API_TOKEN")
JSTREAM_TENANT_KEY      = os.getenv("JSTREAM_TENANT_KEY")
JSTREAM_CLIENT_KEY      = os.getenv("JSTREAM_CLIENT_KEY")
JSTREAM_CLIENT_SECRET   = os.getenv("JSTREAM_CLIENT_SECRET")
JWT_SECRET              = os.getenv("JWT_SECRET")
JWT_EXP                 = int(os.getenv("JWT_EXP"))

STATIC_PAGE_URL         = config["page"]["url"]
ALLOWED_ORIGINS_STR     = config["page"]["cors"]["origin"]
ALLOWED_METHODS_STR     = config["page"]["cors"]["method"]
ALLOWED_HEADERS_STR     = config["page"]["cors"]["header"]

PRETIX_API_BASE         = config["api"]["pretix"]["base"]
PRETIX_ORGANIZER        = config["api"]["pretix"]["organizer"]
REDIRECT_URI            = config["api"]["pretix"]["redirect_uri"]

JSTREAM_API_LIVE        = config["api"]["jstream"]["wlive"]
JSTREAM_API_AUTH        = config["api"]["jstream"]["hlsauth"]
JSTREAM_API_SESSION     = config["api"]["jstream"]["session"]

LIVE_TICKET_ID          = config["live"]["pretix_live_ticket_id"]


# 必須の環境変数のチェック
REQUIRED_ENV = [
    "PRETIX_CLIENT_ID", "PRETIX_CLIENT_SECRET", "PRETIX_API_TOKEN",
    "JSTREAM_TENANT_KEY", "JSTREAM_CLIENT_KEY", "JSTREAM_CLIENT_SECRET",
    "JWT_SECRET", "JWT_EXP"
]
for var in REQUIRED_ENV:
    if not os.getenv(var):
        raise ValueError(f"Missing required environment variable: {var}")

# --------------------------
# FastAPI 初期化
# --------------------------
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

    # 1. Pretixアクセストークン取得
    try:
        token_resp = await client.post(
            f"{PRETIX_API_BASE}/{PRETIX_ORGANIZER}/oauth2/v1/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": PRETIX_CLIENT_ID,
                "client_secret": PRETIX_CLIENT_SECRET,
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
            f"{PRETIX_API_BASE}/{PRETIX_ORGANIZER}/oauth2/v1/userinfo",
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
        orders_url = f"{PRETIX_API_BASE}/api/v1/organizers/{PRETIX_ORGANIZER}/orders/?email={quote(email)}"
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

    # 5. JWT生成
    payload = {
        "email": email,
        "has_ticket": has_ticket,
        "exp": int(time.time()) + JWT_EXP,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    logger.info(f"Generated JWT: {token}")

    # 6. 静的ページにリダイレクト
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
            "has_ticket": decoded["has_ticket"],
            "stream_id": decoded.get("stream_id"),
            "content_id": decoded.get("content_id"),
            "session_id": decoded.get("session_id")
        }
    except jwt.ExpiredSignatureError:
        logger.warning("JWT expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
