import httpx
from app.core.logger import logger
from app.core.config import *

class JstreamServiceError(Exception):
    pass

async def get_jstream_client_credentials_token(client: httpx.AsyncClient) -> str:
    logger.info("J-Stream Access Token取得APIを呼び出します")
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
            logger.info("J-Stream Access Tokenの取得に成功しました")
        return access_token
    except httpx.HTTPStatusError as e:
        logger.error(f"J-Stream Access Token取得エラー: {e.response.status_code} - {e.response.text}")
        raise JstreamServiceError(f"J-Stream Access Tokenの取得に失敗しました: {e.response.text}")
    except Exception as e:
        logger.error(f"J-Stream Access Token取得中に予期せぬエラーが発生しました: {e}")
        raise JstreamServiceError("J-Stream Access Token取得中にエラーが発生しました")