from datetime import datetime, timedelta
import os

from fastapi import APIRouter
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
import httpx
import pycountry
import pytz

router = APIRouter()

TZ = os.environ.get("TIMEZONE", "UTC").strip()
if TZ not in pytz.all_timezones:
    raise ValueError("Invalid time zone selection")
MT = pytz.timezone(TZ)


@router.on_event("startup")
async def startup():
    FastAPICache.init(InMemoryBackend())


def country_to_code(country_name: str) -> str:
    replacements = {
        "Great Britain": "GB",
        "United States": "US",
    }
    try:
        country_name = replacements.get(country_name, country_name)
        return pycountry.countries.lookup(country_name).alpha_2.lower()
    except Exception:
        return ""


def get_target_season() -> int:
    raw = os.environ.get("F1_SEASON", "auto").strip().lower()
    if raw in ("", "auto", "current"):
        return datetime.now(MT).year
    if raw.isdigit():
        return int(raw)
    return datetime.now(MT).year


async def fetch_constructors_data(client: httpx.AsyncClient, season: int):
    urls = [
        f"https://f1api.dev/api/{season}/constructors-championship",
        "https://f1api.dev/api/current/constructors-championship",
    ]

    for url in urls:
        try:
            response = await client.get(url, timeout=20)
            if response.status_code == 200:
                return response.json()
        except Exception:
            continue

    return None


@router.get("/", summary="Fetch current constructors championship")
async def get_constructors_championship():
    cache = FastAPICache.get_backend()
    target_season = get_target_season()
    cache_key = f"constructors_championship:{target_season}"

    cached = await cache.get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        data = await fetch_constructors_data(client, target_season)
        if not data:
            return {"error": "Failed to fetch data"}

    constructors = data.get("constructors_championship", [])
    results = []
    for entry in constructors:
        team = entry.get("team", {})
        team_name = team.get("teamName")
        for word in ["Formula 1", "F1", "Racing", "Team", "Scuderia"]:
            if team_name:
                team_name = team_name.replace(word, "").strip()
        country = team.get("country", "")
        results.append(
            {
                "team": team_name,
                "position": entry.get("position"),
                "points": entry.get("points"),
                "wins": entry.get("wins") or 0,
                "country": country,
                "flag": country_to_code(country),
                "wiki": team.get("url"),
            }
        )

    # Avoid calling the heavier next_race endpoint here just to derive a TTL.
    expire = 3600
    expiry_dt = datetime.now(MT) + timedelta(seconds=expire)

    response_data = {
        "season": data.get("season"),
        "cache_expires": expiry_dt.isoformat(),
        "constructors": results,
    }

    await cache.set(cache_key, response_data, expire=expire)
    return response_data
