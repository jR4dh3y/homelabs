from datetime import datetime, timedelta
import os

from fastapi import APIRouter
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
import fastf1
import httpx
import pytz

router = APIRouter()

TZ = os.environ.get("TIMEZONE", "UTC").strip()
if TZ not in pytz.all_timezones:
    raise ValueError("Invalid time zone selection")
MT = pytz.timezone(TZ)
UTC = pytz.utc


@router.on_event("startup")
async def startup():
    FastAPICache.init(InMemoryBackend())


def convert_to_mt(date_str, time_str):
    if not date_str or not time_str:
        return None
    dt_utc = datetime.strptime(f"{date_str}T{time_str}", "%Y-%m-%dT%H:%M:%SZ")
    dt_utc = UTC.localize(dt_utc)
    return dt_utc.astimezone(MT)


def get_target_season() -> int:
    raw = os.environ.get("F1_SEASON", "auto").strip().lower()
    if raw in ("", "auto", "current"):
        return datetime.now(MT).year
    if raw.isdigit():
        return int(raw)
    return datetime.now(MT).year


def session_display_name(session_name: str) -> str:
    readable = {
        "fp1": "Free Practice 1",
        "fp2": "Free Practice 2",
        "fp3": "Free Practice 3",
        "qualy": "Qualifying",
        "sprintQualy": "Sprint Qualifying",
        "sprintRace": "Sprint Race",
        "race": "Race",
    }
    return readable.get(session_name, session_name.title())


def session_fastf1_code(session_name: str) -> str:
    session_codes = {
        "fp1": "FP1",
        "fp2": "FP2",
        "fp3": "FP3",
        "qualy": "Q",
        "sprintQualy": "SQ",
        "sprintRace": "S",
        "race": "R",
    }
    return session_codes.get(session_name, session_name.upper())


def parse_session_datetime(date_str, time_str):
    if not date_str or not time_str:
        return None
    try:
        return convert_to_mt(date_str, time_str)
    except Exception:
        return None


def format_session_time(dt):
    if not dt:
        return None
    return {
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%-I:%M%p"),
        "datetime": dt.isoformat(),
    }


def sort_races_by_date(calendar_data):
    return sorted(
        calendar_data.get("races", []),
        key=lambda race: race.get("schedule", {}).get("race", {}).get("date", ""),
    )


def parse_race_datetime_utc(race):
    race_date_str = race.get("schedule", {}).get("race", {}).get("date")
    race_time_str = race.get("schedule", {}).get("race", {}).get("time")
    if not race_date_str or not race_time_str:
        return None

    try:
        return UTC.localize(datetime.strptime(f"{race_date_str}T{race_time_str}", "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None


def find_upcoming_races(calendar_data):
    now = datetime.now(UTC)
    upcoming = []

    for race in sort_races_by_date(calendar_data):
        race_datetime = parse_race_datetime_utc(race)
        if race_datetime and race_datetime >= now:
            upcoming.append(race)

    return upcoming


def enrich_race_payload(race, season):
    schedule = race.get("schedule", {})
    for session, val in schedule.items():
        if val.get("date") and val.get("time"):
            dt_mt = convert_to_mt(val["date"], val["time"])
            val["date"] = dt_mt.strftime("%Y-%m-%d")
            val["time"] = dt_mt.strftime("%-I:%M%p")
            val["datetime_rfc3339"] = dt_mt.isoformat()

    calendar_round = race.get("round")
    try:
        event_details = fastf1.get_event(
            year=int(season) if season is not None else season,
            gp=int(calendar_round) if calendar_round is not None else calendar_round,
        )
        race["raceName"] = event_details.EventName
    except Exception as err:
        print(f"FastF1 event lookup failed for season={season} round={calendar_round}: {err}")
        race["raceName"] = (
            race.get("raceName")
            or race.get("competition", {}).get("name")
            or "Unknown Grand Prix"
        )

    circuit = race.get("circuit", {})
    if "circuitLength" in circuit:
        try:
            raw_length = int(circuit["circuitLength"].replace("km", "").strip())
            circuit["circuitLengthKm"] = raw_length / 1000.0
        except Exception:
            circuit["circuitLengthKm"] = None

    fastest_driver_id = circuit.get("fastestLapDriverId")
    if fastest_driver_id:
        name_parts = fastest_driver_id.replace("_", " ").split(" ")
        circuit["fastestLapDriverName"] = name_parts[-1].capitalize()

    fastest_lap_time = circuit.get("lapRecord")
    if fastest_lap_time:
        circuit["lapRecord"] = ".".join(fastest_lap_time.rsplit(":", 1))

    laps = race.get("laps")
    if laps and circuit.get("circuitLengthKm") is not None:
        race["totalDistanceKm"] = round(laps * circuit["circuitLengthKm"], 2)
    else:
        race["totalDistanceKm"] = None

    return race


def build_race_summary_response(calendar_data, race, cache_key, expire=3600):
    cache = FastAPICache.get_backend()
    expiry_dt = datetime.now(MT) + timedelta(seconds=expire)
    response_data = {
        "season": calendar_data.get("season"),
        "round": race.get("round"),
        "timezone": TZ,
        "cache_expires": expiry_dt.isoformat(),
        "race": [race],
    }
    return cache, response_data


def format_result_value(value):
    if value is None:
        return ""

    if hasattr(value, "to_pytimedelta"):
        value = value.to_pytimedelta()

    if isinstance(value, timedelta):
        total_ms = int(round(value.total_seconds() * 1000))
        if total_ms < 0:
            total_ms = abs(total_ms)
        hours, remainder = divmod(total_ms, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        seconds, milliseconds = divmod(remainder, 1000)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
        return f"{minutes}:{seconds:02d}.{milliseconds:03d}"

    text = str(value).strip()
    if text in ("", "NaT", "nan", "None"):
        return ""
    return text


def extract_result_detail(row):
    for field in ("Q3", "Q2", "Q1", "Time"):
        formatted = format_result_value(row.get(field))
        if formatted:
            if field.startswith("Q"):
                return f"{field} {formatted}"
            return formatted

    status = str(row.get("Status") or "").strip()
    if status and status.lower() != "finished":
        return status
    return ""


def extract_points(value):
    try:
        numeric = float(value)
    except Exception:
        return None
    if numeric != numeric:
        return None
    if numeric.is_integer():
        return int(numeric)
    return round(numeric, 1)


def normalize_compound(compound):
    text = str(compound or "").strip().lower()
    mapping = {
        "soft": "S",
        "medium": "M",
        "hard": "H",
        "intermediate": "I",
        "wet": "R",
    }
    return mapping.get(text, "")


def parse_intish(value):
    try:
        numeric = float(value)
    except Exception:
        return None

    if numeric != numeric:
        return None

    return int(numeric)


def is_qualifying_session(session_key: str) -> bool:
    return session_key in ("qualy", "sprintQualy")


def is_practice_session(session_key: str) -> bool:
    return session_key in ("fp1", "fp2", "fp3")


def is_race_session(session_key: str) -> bool:
    return session_key in ("race", "sprintRace")


def format_delta(value):
    if value is None:
        return ""

    if hasattr(value, "to_pytimedelta"):
        value = value.to_pytimedelta()

    if not isinstance(value, timedelta):
        return ""

    total_ms = int(round(value.total_seconds() * 1000))
    sign = "-" if total_ms < 0 else "+"
    total_ms = abs(total_ms)
    minutes, remainder = divmod(total_ms, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    if minutes:
        return f"{sign}{minutes}:{seconds:02d}.{milliseconds:03d}"
    return f"{sign}{seconds}.{milliseconds:03d}"


def extract_reference_time(row):
    for field in ("Q3", "Q2", "Q1", "Time"):
        value = row.get(field)
        formatted = format_result_value(value)
        if formatted:
            return value
    return None


def build_driver_session_meta(session):
    laps = getattr(session, "laps", None)
    if laps is None or laps.empty:
        return {}

    meta = {}
    for driver_code, driver_laps in laps.groupby("Driver"):
        ordered_laps = driver_laps.sort_values(["LapNumber", "Stint"], na_position="last")
        completed_laps = 0
        if "LapTime" in ordered_laps.columns:
            completed_laps = int(ordered_laps["LapTime"].notna().sum())

        tyre_sequence = []
        if "Stint" in ordered_laps.columns and "Compound" in ordered_laps.columns:
            stint_values = ordered_laps["Stint"].dropna()
            if not stint_values.empty:
                for stint in sorted(stint_values.unique()):
                    stint_laps = ordered_laps[ordered_laps["Stint"] == stint]
                    compounds = [normalize_compound(value) for value in stint_laps["Compound"].tolist()]
                    compound = next((value for value in compounds if value), "")
                    if compound and (not tyre_sequence or tyre_sequence[-1] != compound):
                        tyre_sequence.append(compound)

        if not tyre_sequence and "Compound" in ordered_laps.columns:
            for raw_compound in ordered_laps["Compound"].tolist():
                compound = normalize_compound(raw_compound)
                if compound and (not tyre_sequence or tyre_sequence[-1] != compound):
                    tyre_sequence.append(compound)

        meta[str(driver_code)] = {
            "laps_completed": completed_laps,
            "tyre_sequence": tyre_sequence,
            "tyre_sequence_text": ",".join(tyre_sequence),
        }

    return meta


def build_qualifying_position_map(session):
    results = getattr(session, "results", None)
    if results is None or results.empty:
        return {}

    mapping = {}
    for _, row in results.iterrows():
        abbreviation = str(row.get("Abbreviation") or "").strip()
        position = parse_intish(row.get("Position"))
        if abbreviation and position is not None:
            mapping[abbreviation] = position
    return mapping


def build_grid_reference_map(year: int, round_number: int, session_key: str):
    compare_code = None
    if session_key == "race":
        compare_code = "Q"
    elif session_key == "sprintRace":
        compare_code = "SQ"

    if not compare_code:
        return {}

    try:
        compare_session = fastf1.get_session(year, round_number, compare_code)
        compare_session.load(laps=False, telemetry=False, weather=False, messages=False)
        return build_qualifying_position_map(compare_session)
    except Exception:
        return {}


def build_best_lap_meta(session):
    laps = getattr(session, "laps", None)
    if laps is None or laps.empty:
        return {}

    timed_laps = laps.dropna(subset=["LapTime"])
    if timed_laps.empty:
        return {}

    accurate_laps = timed_laps
    if "IsAccurate" in timed_laps.columns:
        accurate_only = timed_laps[timed_laps["IsAccurate"] == True]
        if not accurate_only.empty:
            accurate_laps = accurate_only

    session_name = str(getattr(session, "name", "") or "").strip().lower()
    qualifying_like = session_name in ("qualifying", "sprint qualifying")

    best_sector_times = {}
    if qualifying_like:
        for index in range(1, 4):
            sector_key = f"Sector{index}Time"
            sector_laps = accurate_laps.dropna(subset=[sector_key])
            if not sector_laps.empty:
                best_sector_times[sector_key] = sector_laps[sector_key].min()

    meta = {}
    for driver_code, driver_laps in accurate_laps.groupby("Driver"):
        best_idx = driver_laps["LapTime"].idxmin()
        best_lap = driver_laps.loc[best_idx]
        driver_best_sector_times = {}
        for index in range(1, 4):
            sector_key = f"Sector{index}Time"
            driver_sector_laps = driver_laps.dropna(subset=[sector_key])
            if not driver_sector_laps.empty:
                driver_best_sector_times[sector_key] = driver_sector_laps[sector_key].min()

        sector_marks = []
        for index in range(1, 4):
            sector_key = f"Sector{index}Time"
            sector_value = best_lap.get(sector_key)
            if sector_value is None or str(sector_value).strip() in ("", "NaT", "nan", "None"):
                sector_marks.append("gray")
                continue

            if qualifying_like and sector_key in best_sector_times and sector_value == best_sector_times[sector_key]:
                sector_marks.append("purple")
            elif sector_key in driver_best_sector_times and sector_value == driver_best_sector_times[sector_key]:
                sector_marks.append("green")
            else:
                sector_marks.append("gray")

        meta[str(driver_code)] = {
            "lap_time": best_lap.get("LapTime"),
            "detail": format_result_value(best_lap.get("LapTime")),
            "compound": normalize_compound(best_lap.get("Compound")),
            "compound_full": str(best_lap.get("Compound") or "").strip(),
            "fresh_tyre": bool(best_lap.get("FreshTyre")) if best_lap.get("FreshTyre") is not None else None,
            "sector_marks": sector_marks,
        }

    return meta


def build_lap_based_results(session):
    best_lap_meta = build_best_lap_meta(session)
    if not best_lap_meta:
        return []

    driver_session_meta = build_driver_session_meta(session)
    results_frame = getattr(session, "results", None)
    driver_meta = {}
    if results_frame is not None and not results_frame.empty:
        for _, row in results_frame.iterrows():
            code = str(row.get("Abbreviation") or "").strip()
            full_name = str(row.get("FullName") or "").strip()
            if code:
                driver_meta[code] = {
                    "driver": full_name or code,
                    "surname": full_name.split(" ")[-1] if full_name else code,
                    "team": str(row.get("TeamName") or row.get("Team") or "").strip(),
                }

    classification = []
    for driver_code, lap_meta in best_lap_meta.items():
        meta = driver_meta.get(driver_code, {})
        session_meta = driver_session_meta.get(driver_code, {})
        driver_name = meta.get("driver") or str(driver_code)
        classification.append(
            {
                "position": 0,
                "driver": driver_name,
                "surname": meta.get("surname") or driver_name.split(" ")[-1],
                "abbreviation": str(driver_code),
                "team": meta.get("team") or "",
                "detail": lap_meta.get("detail") or "",
                "status": "",
                "points": None,
                "compound": lap_meta.get("compound") or "",
                "compound_full": lap_meta.get("compound_full") or "",
                "fresh_tyre": lap_meta.get("fresh_tyre"),
                "sector_marks": lap_meta.get("sector_marks") or [],
                "laps_completed": session_meta.get("laps_completed") or 0,
                "tyre_sequence": session_meta.get("tyre_sequence") or [],
                "tyre_sequence_text": session_meta.get("tyre_sequence_text") or "",
                "leader_gap": "",
                "ahead_gap": "",
                "grid_delta": 0,
                "grid_delta_text": "0",
                "penalty_flag": False,
                "penalty_marker": "",
                "_lap_time_sort": lap_meta.get("lap_time"),
            }
        )

    classification.sort(key=lambda item: item["_lap_time_sort"])
    for index, item in enumerate(classification, start=1):
        item["position"] = index
        item.pop("_lap_time_sort", None)

    return classification


async def fetch_calendar_data(client: httpx.AsyncClient, season: int):
    urls = [
        f"https://f1api.dev/api/{season}",
        "https://f1api.dev/api/current",
    ]

    for url in urls:
        try:
            response = await client.get(url, timeout=20)
            if response.status_code == 200:
                return response.json()
        except Exception:
            continue

    return None


async def build_last_completed_session_payload(calendar_data, target_season: int):
    races = calendar_data.get("races", [])
    now = datetime.now(MT)
    completed_sessions = []
    upcoming_sessions = []

    for race in races:
        schedule = race.get("schedule", {})
        for session_name, session_data in schedule.items():
            session_dt = parse_session_datetime(session_data.get("date"), session_data.get("time"))
            if not session_dt:
                continue

            session_item = {
                "round": race.get("round"),
                "session_key": session_name,
                "session_name": session_display_name(session_name),
                "session_dt": session_dt,
                "race": race,
            }

            if session_dt <= now:
                completed_sessions.append(session_item)
            else:
                upcoming_sessions.append(session_item)

    if not completed_sessions:
        return {"message": "No completed sessions found yet"}

    completed_sessions.sort(key=lambda item: item["session_dt"])
    upcoming_sessions.sort(key=lambda item: item["session_dt"])

    last_session = completed_sessions[-1]
    next_session = upcoming_sessions[0] if upcoming_sessions else None

    race = last_session["race"]
    round_number = race.get("round")
    event_name = (
        race.get("raceName")
        or race.get("competition", {}).get("name")
        or "Unknown Grand Prix"
    )
    circuit = race.get("circuit", {})

    results = []
    load_error = None

    try:
        season = int(calendar_data.get("season") or target_season)
        session = fastf1.get_session(
            season,
            int(round_number),
            session_fastf1_code(last_session["session_key"]),
        )
        session.load(telemetry=False, weather=False, messages=False)
        event_name = getattr(getattr(session, "event", None), "EventName", None) or event_name
        best_lap_meta = build_best_lap_meta(session)
        driver_session_meta = build_driver_session_meta(session)
        grid_reference_map = build_grid_reference_map(season, int(round_number), last_session["session_key"])

        results_frame = getattr(session, "results", None)
        qualifying_reference_times = {}
        if results_frame is not None and not results_frame.empty:
            for _, row in results_frame.iterrows():
                position = parse_intish(row.get("Position"))
                if position is None:
                    continue

                full_name = str(row.get("FullName") or "").strip()
                abbreviation = str(row.get("Abbreviation") or "").strip()
                lap_meta = best_lap_meta.get(abbreviation, {})
                session_meta = driver_session_meta.get(abbreviation, {})
                grid_position = parse_intish(row.get("GridPosition"))
                qualifying_reference_times[abbreviation] = extract_reference_time(row)
                qualifying_position = grid_reference_map.get(abbreviation)
                grid_delta = 0 if grid_position is None else grid_position - position
                penalty_flag = bool(
                    qualifying_position is not None
                    and grid_position is not None
                    and grid_position > qualifying_position
                )
                results.append(
                    {
                        "position": position,
                        "driver": full_name or abbreviation,
                        "surname": (full_name.split(" ")[-1] if full_name else abbreviation),
                        "abbreviation": abbreviation,
                        "team": str(row.get("TeamName") or "").strip(),
                        "detail": extract_result_detail(row) or lap_meta.get("detail") or "",
                        "status": str(row.get("Status") or "").strip(),
                        "points": extract_points(row.get("Points")),
                        "compound": lap_meta.get("compound") or "",
                        "compound_full": lap_meta.get("compound_full") or "",
                        "fresh_tyre": lap_meta.get("fresh_tyre"),
                        "sector_marks": lap_meta.get("sector_marks") or [],
                        "laps_completed": session_meta.get("laps_completed") or 0,
                        "tyre_sequence": session_meta.get("tyre_sequence") or [],
                        "tyre_sequence_text": session_meta.get("tyre_sequence_text") or "",
                        "leader_gap": "",
                        "ahead_gap": "",
                        "grid_delta": grid_delta,
                        "grid_delta_text": f"+{grid_delta}" if grid_delta > 0 else str(grid_delta),
                        "penalty_flag": penalty_flag,
                        "penalty_marker": "!" if penalty_flag else "",
                    }
                )

            results.sort(key=lambda item: item["position"])

            if is_qualifying_session(last_session["session_key"]):
                leader_reference = None
                previous_reference = None
                for item in results:
                    reference = qualifying_reference_times.get(item["abbreviation"])
                    if reference is None:
                        item["leader_gap"] = ""
                        item["ahead_gap"] = ""
                        continue

                    if leader_reference is None:
                        leader_reference = reference
                    item["leader_gap"] = "LEAD" if item["position"] == 1 else format_delta(reference - leader_reference)
                    item["ahead_gap"] = "-" if previous_reference is None else format_delta(reference - previous_reference)
                    previous_reference = reference

        if not results:
            results = build_lap_based_results(session)
    except Exception as err:
        load_error = str(err)

    session_info = format_session_time(last_session["session_dt"]) or {}
    next_session_info = format_session_time(next_session["session_dt"]) if next_session else None

    return {
        "season": calendar_data.get("season") or target_season,
        "round": round_number,
        "event_name": event_name,
        "session": {
            "key": last_session["session_key"],
            "name": last_session["session_name"],
            **session_info,
        },
        "next_session": (
            {
                "key": next_session["session_key"],
                "name": next_session["session_name"],
                **(next_session_info or {}),
            }
            if next_session
            else None
        ),
        "circuit": {
            "name": circuit.get("circuitName"),
            "city": circuit.get("city"),
            "country": circuit.get("country"),
        },
        "podium": results[:3],
        "results": results[:10],
        "result_count": len(results),
        "load_error": load_error,
    }


async def fetch_circuit_weather(city: str, country: str):
    if not city:
        return None

    async with httpx.AsyncClient() as client:
        try:
            geo_resp = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={
                    "name": city,
                    "count": 10,
                    "language": "en",
                    "format": "json",
                },
                timeout=20,
            )
            if geo_resp.status_code != 200:
                return None

            results = geo_resp.json().get("results", [])
            if not results:
                return None

            country_norm = (country or "").strip().lower()
            chosen = results[0]
            for item in results:
                item_country = (item.get("country") or "").strip().lower()
                if country_norm and item_country == country_norm:
                    chosen = item
                    break

            lat = chosen.get("latitude")
            lon = chosen.get("longitude")
            if lat is None or lon is None:
                return None

            weather_resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "forecast_days": 1,
                    "timezone": TZ,
                },
                timeout=20,
            )
            if weather_resp.status_code != 200:
                return None

            data = weather_resp.json()
            current = data.get("current", {})
            daily = data.get("daily", {})

            daily_summary = {
                "temperature_2m_max": (daily.get("temperature_2m_max") or [None])[0],
                "temperature_2m_min": (daily.get("temperature_2m_min") or [None])[0],
                "precipitation_probability_max": (daily.get("precipitation_probability_max") or [None])[0],
            }

            return {
                "location": {
                    "city": chosen.get("name") or city,
                    "country": chosen.get("country") or country,
                    "latitude": lat,
                    "longitude": lon,
                },
                "current": current,
                "daily": daily_summary,
                "updated_at": current.get("time"),
            }
        except Exception as err:
            print("Weather fetch failed:", err)
            return None


@router.get("/", summary="Fetch next race")
async def get_next_race():
    cache = FastAPICache.get_backend()
    cache_key = "f1:next_race"

    cached = await cache.get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        try:
            calendar_data = await fetch_calendar_data(client, get_target_season())
            if not calendar_data:
                return {"error": "Failed to fetch race schedule"}
        except Exception as err:
            return {"error": f"Exception while fetching: {err}"}

    upcoming_races = find_upcoming_races(calendar_data)
    next_race = upcoming_races[0] if upcoming_races else None

    if not next_race:
        return {"message": "No upcoming race found"}

    last_completed_session = await build_last_completed_session_payload(
        calendar_data,
        int(calendar_data.get("season") or get_target_season()),
    )

    next_race = enrich_race_payload(next_race, calendar_data.get("season"))
    schedule = next_race.get("schedule", {})
    circuit = next_race.get("circuit", {})

    def get_datetime(item):
        dt_str = item[1].get("datetime_rfc3339")
        try:
            return datetime.fromisoformat(dt_str) if dt_str else datetime.max.replace(tzinfo=MT)
        except Exception:
            return datetime.max.replace(tzinfo=MT)

    sorted_schedule = sorted(schedule.items(), key=get_datetime)

    try:
        detail_level = os.environ.get("EVENT_DETAIL", "main").strip()
    except Exception:
        detail_level = "main"

    next_event = None
    for session_name, session_data in sorted_schedule:
        event_datetime_str = session_data.get("datetime_rfc3339")
        event_date_str = session_data.get("date")
        event_time_str = session_data.get("time")
        if not event_datetime_str:
            continue

        if detail_level == "main":
            if session_name in ("fp1", "fp2", "fp3"):
                continue
        elif detail_level == "race":
            if session_name not in ("race", "sprintRace"):
                continue
        elif detail_level != "detailed":
            raise ValueError("Select one of: 'main', 'race', or 'detailed'.")

        try:
            dt = datetime.fromisoformat(event_datetime_str)
            if dt > datetime.now(MT):
                next_event = {
                    "session": session_display_name(session_name),
                    "date": event_date_str,
                    "time": event_time_str,
                    "datetime": event_datetime_str,
                }
                break
        except Exception:
            continue

    circuit_weather = await fetch_circuit_weather(circuit.get("city"), circuit.get("country"))

    # Keep this endpoint fresh because it now includes live weather data.
    try:
        race_dt_str = (next_event or {}).get("datetime")
        if race_dt_str:
            race_dt = datetime.fromisoformat(race_dt_str).astimezone(MT)
            race_expire = int((race_dt + timedelta(hours=4.25) - datetime.now(MT)).total_seconds())
            if race_expire > 0:
                expire = min(3600, race_expire)
            else:
                expire = 3600
        else:
            expire = 3600
    except Exception:
        expire = 3600

    expire = max(300, expire)
    expiry_dt = datetime.now(MT) + timedelta(seconds=expire)

    response_data = {
        "season": calendar_data.get("season"),
        "round": next_race.get("round"),
        "timezone": TZ,
        "next_event": next_event,
        "cache_expires": expiry_dt.isoformat(),
        "race": [next_race],
        "circuit_weather": circuit_weather,
        "last_session": last_completed_session,
    }

    await cache.set(cache_key, response_data, expire=expire)
    return response_data


@router.get("/following/", summary="Fetch race after the current one")
async def get_following_race():
    cache = FastAPICache.get_backend()
    cache_key = "f1:following_race"

    cached = await cache.get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        try:
            calendar_data = await fetch_calendar_data(client, get_target_season())
            if not calendar_data:
                return {"error": "Failed to fetch race schedule"}
        except Exception as err:
            return {"error": f"Exception while fetching: {err}"}

    upcoming_races = find_upcoming_races(calendar_data)
    following_race = upcoming_races[1] if len(upcoming_races) > 1 else None

    if not following_race:
        return {"message": "No additional upcoming race found"}

    following_race = enrich_race_payload(following_race, calendar_data.get("season"))
    expire = 3600
    _, response_data = build_race_summary_response(calendar_data, following_race, cache_key, expire=expire)

    await cache.set(cache_key, response_data, expire=expire)
    return response_data


@router.get("/last_session/", summary="Fetch most recent completed session")
async def get_last_completed_session():
    cache = FastAPICache.get_backend()
    target_season = get_target_season()
    cache_key = f"f1:last_session:{target_season}"

    cached = await cache.get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        calendar_data = await fetch_calendar_data(client, target_season)
        if not calendar_data:
            return {"error": "Failed to fetch race schedule"}
    expire = 900
    response_data = await build_last_completed_session_payload(calendar_data, target_season)
    response_data["cache_expires"] = (datetime.now(MT) + timedelta(seconds=expire)).isoformat()

    await cache.set(cache_key, response_data, expire=expire)
    return response_data
