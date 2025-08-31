# app/config.py
import os
import tomllib
from dotenv import load_dotenv
from app.logger import logger

load_dotenv()

# 必須環境変数の取得とチェック
REQUIRED_ENV = [
    "PRETIX_CLIENT_ID",
    "PRETIX_CLIENT_SECRET",
    "PRETIX_API_TOKEN",
    "JSTREAM_TENANT_KEY",
    "JSTREAM_CLIENT_KEY",
    "JSTREAM_CLIENT_SECRET",
    "JWT_SECRET",
]

try:
    for var in REQUIRED_ENV:
        if not os.getenv(var):
            raise ValueError(f"Missing required environment variable: {var}")
            
    PRETIX_CLIENT_ID = os.environ["PRETIX_CLIENT_ID"]
    PRETIX_CLIENT_SECRET = os.environ["PRETIX_CLIENT_SECRET"]
    PRETIX_API_TOKEN = os.environ["PRETIX_API_TOKEN"]
    JSTREAM_TENANT_KEY = os.environ["JSTREAM_TENANT_KEY"]
    JSTREAM_CLIENT_KEY = os.environ["JSTREAM_CLIENT_KEY"]
    JSTREAM_CLIENT_SECRET = os.environ["JSTREAM_CLIENT_SECRET"]
    JWT_SECRET = os.environ["JWT_SECRET"]
    
    # JWT有効期限の取得（デフォルト値付き）
    try:
        JWT_EXP = int(os.getenv("JWT_EXP", 300))
    except (ValueError, TypeError):
        logger.warning("警告: JWT_EXPが無効なため、デフォルト値300を使用します。")
        JWT_EXP = 300

except KeyError as e:
    logger.error(f"エラー: 必須の環境変数 {e} が設定されていません。")
    raise ValueError(f"Required environment variable {e} is not set.")

# 設定ファイルの読み込み（ワーカーの作業ディレクトリを基準に探す）
try:
    with open('config.toml', 'rb') as f:
        config = tomllib.load(f)
except FileNotFoundError:
    logger.error("設定ファイル 'config.toml' が見つかりません。")
    raise
except tomllib.TOMLDecodeError:
    logger.error("設定ファイル 'config.toml' の解析に失敗しました。")
    raise

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

LIVE_TICKET_ID          = int(config["live"]["pretix_live_ticket_id"])
LIVE_TRACKS_BY_ID       = {t["track"]: t for t in config["live"]["track"]}
AUTHENTICATED_URL       = config["live"]["authenticated_url"]