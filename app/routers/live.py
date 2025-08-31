from fastapi import APIRouter
from main import config

router = APIRouter()

@router.get("/lives")
async def get_lives():
    return {"lives": config["live"]["track"]}