from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from functools import lru_cache
from pydantic import BaseSettings

# ルーターのインポート
from routers import auth, live, session

# -----------------------------
# 設定
# -----------------------------
class Settings(BaseSettings):
    STATIC_PAGE_URL: str = "https://example.com"
    AUTHENTICATED_URL: str = "https://streaming.example.com/{session_id}"
    LIVE_TICKET_ID: str = "live_ticket"
    PRETIX_API_URL: str = "https://pretix.example.com"
    JSTREAM_API_URL: str = "https://jstream.example.com"

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()

# -----------------------------
# FastAPI インスタンス作成
# -----------------------------
app = FastAPI(title="Key Ticket System")

# -----------------------------
# CORS ミドルウェア
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 必要に応じて制限
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# 依存関数
# -----------------------------
async def get_httpx_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient() as client:
        yield client

# -----------------------------
# ルーター登録
# -----------------------------
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(live.router, prefix="/live", tags=["live"])
app.include_router(session.router, prefix="/session", tags=["session"])