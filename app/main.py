import logging
import os
import time
import json
import io
import asyncio
from contextlib import asynccontextmanager
from urllib.parse import quote
import jwt
import httpx
import tomllib
from fastapi import FastAPI, Request, Query, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from logger import logger
from config import *


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

def get_httpx_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.httpx_client

# --------------------------
# JSTREAMアクセストークン取得ヘルパー関数
# --------------------------
async def _get_jstream_client_credentials_token(client: httpx.AsyncClient) -> str:
    """JSTREAM APIからクライアント認証情報を使ってトークンを取得する"""
    logger.info("JSTREAM クライアントトークン取得APIを呼び出します...")
    try:
        jstream_auth_base_url = "https://" + "/".join(JSTREAM_API_LIVE.split('/')[:1])
        
        response = await client.post(
            f"{jstream_auth_base_url}/v2.0/{JSTREAM_TENANT_KEY}/oauth2/token",
            params={
                "client_key": JSTREAM_CLIENT_KEY,
                "client_secret": JSTREAM_CLIENT_SECRET,
                "grant_type": "client_credentials",
                "resource": f"{jstream_auth_base_url}/"
            }
        )
        response.raise_for_status()
        access_token = response.json().get("access_token")
        if access_token:
            logger.info("JSTREAMクライアントトークンの取得に成功しました。")
        return access_token
    except httpx.HTTPStatusError as e:
        logger.error(f"JSTREAM クライアントトークン取得エラー: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to get JSTREAM client token: {e.response.text}")
    except Exception as e:
        logger.error(f"JSTREAMクライアントトークン取得中に予期せぬエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail="JSTREAMクライアントトークン取得中にエラーが発生しました。")

async def _register_jstream_user(client: httpx.AsyncClient, client_token: str, stream_id: str, email: str) -> None:
    """J-Stream HLS-Authにユーザーを登録する"""
    logger.info(f"J-Stream HLS-Authユーザー登録APIを呼び出します。ユーザー: {email}, ストリームID: {stream_id}...")
    
    # 成功したJavaScriptコードを参考に、JSONペイロードの構造を修正
    email_payload = {"user_id": [email]}
    email_json = json.dumps(email_payload)
    
    try:
        # files引数を使って、JSONデータをファイルとして送信するように修正
        # ファイル名とコンテンツタイプを明示的に指定
        response = await client.put(
            f"https://{JSTREAM_API_AUTH}/{stream_id}/user",
            files={
                'user_list': ('user_list.json', io.BytesIO(email_json.encode('utf-8')), 'application/json')
            },
            headers={"Authorization": f"Bearer {client_token}"}
        )
        response.raise_for_status()
        logger.info(f"ユーザー'{email}'はJ-Stream HLS-Authに正常に登録されました。")
    except httpx.HTTPStatusError as e:
        # HTTPエラー発生時のログ出力
        logger.error("J-Stream HLS-Authユーザー登録エラーが発生しました。")
        logger.error(f"Status Code: {e.response.status_code}")
        logger.error(f"Response Body: {e.response.text}")
        logger.error(f"Request URL: {e.request.url}")
        logger.error(f"Request Method: {e.request.method}")
        logger.error(f"Request Headers: {dict(e.request.headers)}")
        logger.error(f"Request Payload (user_list): {email_json}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to register user with J-Stream HLS-Auth: {e.response.text}")
    except Exception as e:
        # その他の予期せぬエラー発生時のログ出力
        logger.error(f"J-Stream HLS-Authユーザー登録中に予期せぬエラーが発生しました: {e}")
        logger.error(f"Request Payload (user_list): {email_json}")
        raise HTTPException(status_code=500, detail="J-Stream HLS-Authユーザー登録中にエラーが発生しました。")

async def _get_jstream_user_session_id(client: httpx.AsyncClient, client_token: str, email: str, stream_id: str) -> str:
    """ユーザーセッションIDを取得する"""
    logger.info(f"JSTREAM セッションID取得APIを呼び出します。ユーザー: {email}, ストリームID: {stream_id}...")
    try:
        response = await client.post(
            f"https://{JSTREAM_API_SESSION}/service/hlsauth/{stream_id}/session",
            json={
                "email": email,
            },
            headers={
                "Authorization": f"Bearer {client_token}"
            }
        )
        response.raise_for_status()
        session_id = response.json().get("session_id")
        if session_id:
            logger.info(f"JSTREAMセッションIDの取得に成功しました。Session ID: {session_id}")
        return session_id
    except httpx.HTTPStatusError as e:
        logger.error(f"JSTREAM セッションID取得エラー: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to get JSTREAM user session ID: {e.response.text}")
    except Exception as e:
        logger.error(f"JSTREAMセッションID取得中に予期せぬエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail="JSTREAMセッションID取得中にエラーが発生しました。")


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

    # 1. Pretix アクセストークン取得
    logger.info("Pretix アクセストークン取得APIを呼び出します...")
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
        logger.info("Pretix アクセストークンの取得に成功しました。")

    except httpx.HTTPStatusError as e:
        logger.error(f"Pretix アクセストークン取得エラー: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to exchange code for token: {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Pretix アクセストークン取得中にリクエストエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail="Network error during token exchange.")

    # 2. Pretix APIでユーザー情報取得
    logger.info("Pretix ユーザー情報取得APIを呼び出します...")
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
        logger.info("Pretix ユーザー情報取得に成功しました。")

    except httpx.HTTPStatusError as e:
        logger.error(f"Pretix ユーザー情報取得エラー: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to fetch user info: {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Pretix ユーザー情報取得中にリクエストエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail="Network error during user info fetch.")

    # 3. Pretix APIで購入情報取得
    logger.info(f"Pretix 注文情報取得APIを呼び出します。ユーザー: {email}...")
    try:
        orders_url = f"{PRETIX_API_BASE}/api/v1/organizers/{PRETIX_ORGANIZER}/orders/?email={quote(email)}"
        headers = {"Authorization": f"Token {PRETIX_API_TOKEN}"}
        orders_resp = await client.get(orders_url, headers=headers)
        orders_resp.raise_for_status()
        orders_data = orders_resp.json()
        logger.info("Pretix 注文情報取得に成功しました。")

    except httpx.HTTPStatusError as e:
        logger.error(f"Pretix 注文情報取得エラー: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to fetch orders: {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Pretix 注文情報取得中にリクエストエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail="Network error during orders fetch.")

    has_ticket = any(
        pos.get("item") == LIVE_TICKET_ID
        for order in orders_data.get("results", [])
        for pos in order.get("positions", [])
    )
    logger.info(f"ユーザー'{email}'はライブ配信チケットを所有しています: {has_ticket}")

    # 4. チケット所有者向けのJSTREAMユーザー登録
    jstream_registered_tracks = {}
    if has_ticket:
        # 1段階目: クライアントレベルのトークンを取得
        jstream_client_token = await _get_jstream_client_credentials_token(client)

        # すべてのライブトラックに対してユーザーを登録
        for track in config["live"]["track"]:
            stream_id = track.get("stream_id")
            if not stream_id:
                logger.warning(f"警告: トラック {track.get('track')} のストリームIDが設定されていません。")
                continue

            try:
                await _register_jstream_user(client, jstream_client_token, stream_id, email)
                jstream_registered_tracks[stream_id] = True
            except HTTPException as e:
                logger.error(f"ユーザー登録に失敗しました。ストリームID: {stream_id}, エラー: {e.detail}")
                # 特定のトラックで失敗しても、他のトラックの処理を継続
                continue
            
    # 5. JWT生成（email + has_ticket + JSTREAM登録情報）
    payload = {
        "email": email,
        "has_ticket": has_ticket,
        "exp": int(time.time()) + JWT_EXP,
        "jstream_registered_tracks": jstream_registered_tracks
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    logger.info(f"JWTを生成しました。")

    # 6. 静的ページにリダイレクト
    redirect_url = f"{STATIC_PAGE_URL}?token={quote(token)}"
    logger.info(f"静的ページへリダイレクトします: {redirect_url}")
    return RedirectResponse(url=redirect_url)

# --------------------------
# セッションID取得API
# --------------------------
@app.get("/session")
async def get_session_id(
    request: Request,
    token: str = Query(...),
    stream_id: str = Query(...),
    client: httpx.AsyncClient = Depends(get_httpx_client)
):
    try:
        decoded_jwt = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        email = decoded_jwt.get("email")
        
        # 登録済みトラックのチェック
        registered_tracks = decoded_jwt.get("jstream_registered_tracks", {})
        if not registered_tracks.get(stream_id, False):
            raise HTTPException(status_code=403, detail="User is not registered for this stream.")

        # クライアントトークンの取得
        jstream_client_token = await _get_jstream_client_credentials_token(client)

        # ユーザーセッションIDの取得
        session_id = await _get_jstream_user_session_id(client, jstream_client_token, email, stream_id)

        # 再生URLの構築
        playback_url = AUTHENTICATED_URL.replace("{session_id}", session_id)

        return JSONResponse(content={"playback_url": playback_url})
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"セッションID取得中に予期せぬエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail="セッションID取得中にエラーが発生しました。")


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
            "jstream_registered_tracks": decoded.get("jstream_registered_tracks", {})
        }
    except jwt.ExpiredSignatureError:
        logger.warning("JWT expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

# --------------------------
# ライブ情報取得API
# --------------------------
@app.get("/lives")
async def get_lives():
    logger.info("ライブ情報取得リクエストを受信しました。")
    return {"lives": config["live"]["track"]}
