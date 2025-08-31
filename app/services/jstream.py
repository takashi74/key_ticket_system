import os
import logging
import json
import io
import time
from urllib.parse import quote
import httpx
from fastapi import HTTPException
from typing import Dict, Any

logger = logging.getLogger(__name__)

# 共有リソース
_session_cache: Dict[str, Any] = {}
_client_token = ""
_client_token_expiry = 0

# 環境変数と設定からJ-Streamの情報を取得
JSTREAM_API_LIVE = os.getenv("JSTREAM_API_LIVE")
JSTREAM_API_AUTH = os.getenv("JSTREAM_API_AUTH")
JSTREAM_API_SESSION = os.getenv("JSTREAM_API_SESSION")
JSTREAM_API_KEY = os.getenv("JSTREAM_API_KEY")
JSTREAM_API_SECRET = os.getenv("JSTREAM_API_SECRET")

async def get_jstream_client_token(client: httpx.AsyncClient):
    """J-Streamのクライアントトークンを取得またはキャッシュから返す。"""
    global _client_token, _client_token_expiry
    
    if _client_token and _client_token_expiry > time.time():
        logger.info("キャッシュされたクライアントトークンを使用します。")
        return _client_token
    
    logger.info("J-Streamクライアントトークン取得APIを呼び出します...")
    auth_string = f"{JSTREAM_API_KEY}:{JSTREAM_API_SECRET}"
    base64_auth = quote(auth_string.encode('utf-8').hex())
    
    try:
        response = await client.post(
            f"https://{JSTREAM_API_LIVE}/client-token",
            headers={"Authorization": f"Basic {base64_auth}"}
        )
        response.raise_for_status()
        
        token_data = response.json()
        _client_token = token_data.get("client_token")
        expires_in = token_data.get("expires_in", 3600)
        _client_token_expiry = time.time() + expires_in - 60
        
        logger.info("J-Streamクライアントトークンの取得に成功しました。")
        return _client_token
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTPエラーが発生しました: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail="J-Streamクライアントトークンの取得に失敗しました。")
    except Exception as e:
        logger.error(f"J-Streamクライアントトークン取得中にエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail="J-Streamクライアントトークンの取得に失敗しました。")
        
async def register_jstream_user(client: httpx.AsyncClient, client_token: str, stream_id: str, user_email: str):
    """J-Stream HLS-Authにユーザーを登録する。"""
    cache_key = f"{stream_id}:{user_email}"
    if _session_cache.get(cache_key):
        logger.info(f"ユーザー'{user_email}'はJ-Stream HLS-Authに既に登録されています。")
        return
        
    logger.info(f"J-Stream HLS-Authユーザー登録APIを呼び出します。ユーザー: {user_email}, ストリームID: {stream_id}...")
    
    try:
        user_list_data = {"user_id": [user_email]}
        user_list_json = json.dumps(user_list_data)
        user_list_bytes = user_list_json.encode('utf-8')
        
        response = await client.put(
            f"https://{JSTREAM_API_AUTH}/{stream_id}/user",
            headers={
                "Authorization": f"Bearer {client_token}",
            },
            files={
                "user_list": ("user_list.json", io.BytesIO(user_list_bytes), "application/json")
            }
        )
        response.raise_for_status()
        
        _session_cache[cache_key] = True
        
        logger.info(f"ユーザー'{user_email}'はJ-Stream HLS-Authに正常に登録されました。")
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTPエラーが発生しました: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"J-Stream HLS-Authへのユーザー登録に失敗しました: {e.response.text}")
    except Exception as e:
        logger.error(f"J-Stream HLS-Authユーザー登録中に予期せぬエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail="J-Stream HLS-Authへのユーザー登録に失敗しました。")
        
async def get_jstream_session_id(client: httpx.AsyncClient, client_token: str, stream_id: str, user_email: str):
    """J-Stream HLS-AuthのセッションIDを取得する。"""
    logger.info(f"セッションID取得APIを呼び出します。ストリームID: {stream_id}, ユーザーメール: {user_email}...")
    
    try:
        response = await client.post(
            f"https://{JSTREAM_API_SESSION}/service/hlsauth/{stream_id}/session",
            headers={
                "Authorization": f"Bearer {client_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            },
            data={"user_id": user_email}
        )
        response.raise_for_status()
        
        session_data = response.json()
        session_id = session_data.get("session_id")
        
        if not session_id:
            raise ValueError("セッションIDがレスポンスに含まれていません。")
            
        return session_id
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTPエラーが発生しました: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail="J-StreamセッションIDの取得に失敗しました。")
    except Exception as e:
        logger.error(f"J-StreamセッションID取得中にエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail="J-StreamセッションIDの取得に失敗しました。")
