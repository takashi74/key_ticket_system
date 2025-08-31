from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx

from services.jstream import get_client_token, get_session_id
from services.auth import decode_token
from main import get_httpx_client, AUTHENTICATED_URL

router = APIRouter()

@router.get("/session")
async def get_session(
    request: Request,
    token: str = Query(...),
    stream_id: str = Query(...),
    client: httpx.AsyncClient = Depends(get_httpx_client),
):
    decoded = decode_token(token)
    email = decoded.get("email")
    registered_tracks = decoded.get("jstream_registered_tracks", {})

    if not registered_tracks.get(stream_id, False):
        raise HTTPException(status_code=403, detail="User is not registered for this stream.")

    client_token = await get_client_token(client)
    session_id = await get_session_id(client, client_token, email, stream_id)
    playback_url = AUTHENTICATED_URL.replace("{session_id}", session_id)
    return JSONResponse(content={"playback_url": playback_url})