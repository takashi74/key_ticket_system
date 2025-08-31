# core/config.py
import tomllib, os
from dotenv import load_dotenv

load_dotenv()
with open("config.toml", "rb") as f:
    config = tomllib.load(f)

STATIC_PAGE_URL   = config["page"]["url"]
ALLOWED_ORIGINS   = config["page"]["cors"]["origin"].split(",")
ALLOWED_METHODS   = config["page"]["cors"]["method"].split(",")
ALLOWED_HEADERS   = config["page"]["cors"]["header"].split(",")
AUTHENTICATED_URL = config["live"]["authenticated_url"]
LIVE_TICKET_ID    = int(config["live"]["pretix_live_ticket_id"])
