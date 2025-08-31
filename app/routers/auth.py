from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import RedirectResponse
from urllib.parse import quote
import httpx

from services.pretix import get_access_token, get_user_info, get_orders
from services.jstream import get_client_token, register_user
from services.auth import create_token, decode_token
from main import get_httpx_client, config, LIVE_TICKET_ID, STATIC_PAGE_URL

router = APIRouter()

@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(...),
    client: httpx.AsyncClient = Depends(get_httpx_client),
):
    # Pretix
    access_token = await get_access_token(client, code)
    user_info = await get_user_info(client, access_token)
    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email not found in user info.")

    orders = await get_orders(client, email)
    has_ticket = any(
        pos.get("item") == LIVE_TICKET_ID
        for order in orders.get("results", [])
        for pos in order.get("positions", [])
    )

    # JSTREAM
    jstream_registered_tracks = {}
    if has_ticket:
        token = await get_client_token(client)
        for track in config["live"]["track"]:
            stream_id = track.get("stream_id")
            if not stream_id:
                continue
            try:
                await register_user(client, token, stream_id, email)
                jstream_registered_tracks[stream_id] = True
            except HTTPException:
                continue

    # JWT
    jwt_token = create_token(email, has_ticket, jstream_registered_tracks)
    redirect_url = f"{STATIC_PAGE_URL}?token={quote(jwt_token)}"
    return RedirectResponse(url=redirect_url)

@router.get("/verify")
async def verify(token: str = Query(...)):
    decoded = decode_token(token)
    return {
        "email": decoded["email"],
        "has_ticket": decoded["has_ticket"],
        "jstream_registered_tracks": decoded.get("jstream_registered_tracks", {}),
    }