import asyncio
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


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
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


def get_race_schedule_datetimes(race):
    schedule = race.get("schedule", {})
    schedule_items = []

    for session_name, session_data in schedule.items():
        session_dt = parse_iso_datetime(session_data.get("datetime_rfc3339"))
        if not session_dt:
            session_dt = parse_session_datetime(session_data.get("date"), session_data.get("time"))
        if not session_dt:
            continue

        schedule_items.append((session_name, session_data, session_dt))

    schedule_items.sort(key=lambda item: item[2])
    return schedule_items


def find_upcoming_races(calendar_data):
    now = datetime.now(UTC)
    upcoming = []

    for race in sort_races_by_date(calendar_data):
        race_datetime = parse_race_datetime_utc(race)
        if race_datetime and race_datetime >= now:
            upcoming.append(race)

    return upcoming


def session_short_name(session_name: str) -> str:
    readable = {
        "fp1": "FP1",
        "fp2": "FP2",
        "fp3": "FP3",
        "qualy": "Qualifying",
        "sprintQualy": "Sprint Qualifying",
        "sprintRace": "Sprint Race",
        "race": "Race",
    }
    return readable.get(session_name, session_display_name(session_name))


def build_weekend_timeline(race):
    now = datetime.now(MT)
    schedule_items = get_race_schedule_datetimes(race)
    if not schedule_items:
        return []

    last_completed_index = None
    next_index = None

    for index, (_, _, session_dt) in enumerate(schedule_items):
        if session_dt <= now:
            last_completed_index = index
        elif next_index is None:
            next_index = index

    timeline = []
    for index, (session_key, _, session_dt) in enumerate(schedule_items):
        if last_completed_index is not None and index < last_completed_index:
            state = "done"
        elif last_completed_index is not None and index == last_completed_index:
            state = "latest"
        elif next_index is not None and index == next_index:
            state = "next"
        else:
            state = "upcoming"

        state_label = {
            "done": "Done",
            "latest": "Latest",
            "next": "Next",
            "upcoming": "Upcoming",
        }.get(state, "Upcoming")

        timeline.append(
            {
                "key": session_key,
                "name": session_display_name(session_key),
                "short_name": session_short_name(session_key),
                "state": state,
                "state_label": state_label,
                **(format_session_time(session_dt) or {}),
            }
        )

    return timeline


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
        "inter": "I",
        "wet": "W",
        "full wet": "W",
        "extreme wet": "W",
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


def parse_position_value(value):
    position = parse_intish(value)
    if position is None or position <= 0:
        return None
    return position


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


def build_race_gap_meta(session):
    laps = getattr(session, "laps", None)
    if laps is None or laps.empty or "LapTime" not in laps.columns:
        return {}

    totals = {}

    for driver_code, driver_laps in laps.groupby("Driver"):
        valid_laps = driver_laps.dropna(subset=["LapTime"]).sort_values("LapNumber")
        if valid_laps.empty:
            continue

        lap_count = int(valid_laps["LapTime"].notna().sum())
        total_time = valid_laps["LapTime"].sum()
        totals[str(driver_code)] = {
            "lap_count": lap_count,
            "total_time": total_time,
        }

    return totals


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
        # Load with laps so FastF1 can derive qualifying positions from timing data
        # (Ergast is deprecated for 2025+ sessions; lap-derived positions still work).
        compare_session.load(laps=True, telemetry=False, weather=False, messages=False)
        return build_qualifying_position_map(compare_session)
    except Exception:
        return {}


async def fetch_f1api_race_results(season: int, round_number: int) -> dict:
    """
    Fetch race classification from f1api.dev.
    Returns {abbreviation_upper: entry_dict} or {} on failure/missing data.
    Entry dict has: position, grid, time_raw, points, fast_lap, status,
                    driver, surname, abbreviation, team.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://f1api.dev/api/{season}/{round_number}/race",
                timeout=12,
            )
        if resp.status_code != 200:
            return {}
        races = resp.json().get("races", {})
        raw_results = races.get("results") if isinstance(races, dict) else None
        if not raw_results:
            return {}
        mapping = {}
        for entry in raw_results:
            drv = entry.get("driver") or {}
            team = entry.get("team") or {}
            code = str(drv.get("shortName") or "").strip().upper()
            if not code:
                continue
            name = str(drv.get("name") or "").strip()
            surname = str(drv.get("surname") or "").strip()
            full_name = f"{name} {surname}".strip() if name else surname
            grid_raw = parse_intish(entry.get("grid"))
            mapping[code] = {
                "position": parse_intish(entry.get("position")) or 0,
                "grid": grid_raw if grid_raw is not None else 0,
                "time_raw": str(entry.get("time") or "").strip(),
                "points": entry.get("points"),
                "fast_lap": bool(entry.get("fastLap")),
                "status": str(entry.get("retired") or "Finished").strip(),
                "driver": full_name or code,
                "surname": surname or code,
                "abbreviation": code,
                "team": str(team.get("teamName") or "").strip(),
            }
        return mapping
    except Exception:
        return {}


def format_f1api_gap(time_raw: str, position: int) -> str:
    """Convert an f1api.dev race time/gap string to display format."""
    if position == 1:
        return "LEAD"
    t = (time_raw or "").strip()
    if not t or t.lower() in ("none", "null", ""):
        return ""
    # Lapped: "+1 Lap", "+2 Laps", "+1 lap" etc.
    lower = t.lower()
    if "lap" in lower:
        num = "".join(filter(str.isdigit, t))
        return f"+{num}L" if num else t
    # Gap already formatted: "+0.895", "+1:23.456"
    return t


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

    overall_fastest_lap = accurate_laps["LapTime"].min()

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
            "sector_marks_text": "/".join(mark[:1].upper() for mark in sector_marks),
            "fastest_lap": bool(best_lap.get("LapTime") == overall_fastest_lap),
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
                "sector_marks_text": lap_meta.get("sector_marks_text") or "",
                "best_lap_time": lap_meta.get("detail") or "",
                "fastest_lap": bool(lap_meta.get("fastest_lap")),
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

        qualifying_reference_times = {}

        if is_race_session(last_session["session_key"]):
            # ── Primary path: f1api.dev ──────────────────────────────────────
            # Provides correct grid positions (penalties applied), pre-formatted
            # gaps, points, and final classification. FastF1 augments with tyres.
            f1api_results = await fetch_f1api_race_results(season, int(round_number))

            if f1api_results:
                total_starters = len(f1api_results)
                for entry in sorted(f1api_results.values(), key=lambda x: x["position"]):
                    abbreviation = entry["abbreviation"]
                    position = entry["position"]
                    grid = entry["grid"]
                    lap_meta = best_lap_meta.get(abbreviation, {})
                    session_meta = driver_session_meta.get(abbreviation, {})
                    # grid=0 means pit-lane / back-of-grid start
                    starting_position = grid if grid > 0 else total_starters
                    grid_delta = starting_position - position
                    results.append(
                        {
                            "position": position,
                            "driver": entry["driver"],
                            "surname": entry["surname"],
                            "abbreviation": abbreviation,
                            "team": entry["team"],
                            "detail": lap_meta.get("detail") or "",
                            "status": entry["status"],
                            "points": entry["points"],
                            "compound": lap_meta.get("compound") or "",
                            "compound_full": lap_meta.get("compound_full") or "",
                            "fresh_tyre": lap_meta.get("fresh_tyre"),
                            "sector_marks": lap_meta.get("sector_marks") or [],
                            "sector_marks_text": lap_meta.get("sector_marks_text") or "",
                            "best_lap_time": lap_meta.get("detail") or "",
                            "fastest_lap": bool(entry["fast_lap"] or lap_meta.get("fastest_lap")),
                            "laps_completed": session_meta.get("laps_completed") or 0,
                            "tyre_sequence": session_meta.get("tyre_sequence") or [],
                            "tyre_sequence_text": session_meta.get("tyre_sequence_text") or "",
                            "leader_gap": format_f1api_gap(entry["time_raw"], position),
                            "ahead_gap": "",
                            "grid_delta": grid_delta,
                            "grid_delta_text": f"+{grid_delta}" if grid_delta > 0 else str(grid_delta),
                            "penalty_flag": False,
                            "penalty_marker": "",
                        }
                    )
                results.sort(key=lambda x: x["position"])

        if not results:
            # ── Fallback path: FastF1 session.results ────────────────────────
            # Used for qualifying/practice (always), and for races when f1api.dev
            # hasn't published results yet (race day / very recently finished).
            race_gap_meta = build_race_gap_meta(session) if is_race_session(last_session["session_key"]) else {}
            grid_reference_map = build_grid_reference_map(season, int(round_number), last_session["session_key"])

            results_frame = getattr(session, "results", None)
            if results_frame is not None and not results_frame.empty:
                total_starters = len(results_frame)

                for _, row in results_frame.iterrows():
                    position = parse_position_value(row.get("Position"))
                    if position is None:
                        continue

                    full_name = str(row.get("FullName") or "").strip()
                    abbreviation = str(row.get("Abbreviation") or "").strip()
                    lap_meta = best_lap_meta.get(abbreviation, {})
                    session_meta = driver_session_meta.get(abbreviation, {})
                    qualifying_reference_times[abbreviation] = extract_reference_time(row)
                    qualifying_position = grid_reference_map.get(abbreviation)

                    ff1_grid_raw = parse_intish(row.get("GridPosition"))
                    if ff1_grid_raw is not None and ff1_grid_raw > 0:
                        starting_position = ff1_grid_raw
                    elif ff1_grid_raw == 0:
                        starting_position = total_starters
                    else:
                        starting_position = qualifying_position
                    if starting_position is None:
                        starting_position = total_starters

                    grid_delta = 0 if starting_position is None else starting_position - position
                    penalty_flag = bool(
                        qualifying_position is not None
                        and ff1_grid_raw is not None
                        and ff1_grid_raw > 0
                        and ff1_grid_raw > qualifying_position
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
                            "sector_marks_text": lap_meta.get("sector_marks_text") or "",
                            "best_lap_time": lap_meta.get("detail") or "",
                            "fastest_lap": bool(lap_meta.get("fastest_lap")),
                            "laps_completed": session_meta.get("laps_completed") or 0,
                            "tyre_sequence": session_meta.get("tyre_sequence") or [],
                            "tyre_sequence_text": session_meta.get("tyre_sequence_text") or "",
                            "leader_gap": "",
                            "ahead_gap": "",
                            "_raw_time": row.get("Time"),
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
                elif is_race_session(last_session["session_key"]) and results:
                    # FastF1 race gap fallback (f1api.dev not yet available)
                    leader_code = results[0]["abbreviation"]
                    leader_laps = (race_gap_meta.get(leader_code) or {}).get("lap_count") or 0
                    leader_total = (race_gap_meta.get(leader_code) or {}).get("total_time")
                    for item in results:
                        raw_time = item.pop("_raw_time", None)
                        lap_count = (race_gap_meta.get(item["abbreviation"]) or {}).get("lap_count") or 0
                        if item["position"] == 1:
                            item["leader_gap"] = "LEAD"
                        elif leader_laps > 0 and lap_count < leader_laps:
                            item["leader_gap"] = f"+{leader_laps - lap_count}L"
                        else:
                            time_val = raw_time
                            if time_val is not None and hasattr(time_val, "to_pytimedelta"):
                                time_val = time_val.to_pytimedelta()
                            raw_str = str(raw_time) if raw_time is not None else ""
                            if isinstance(time_val, timedelta) and raw_str not in ("", "NaT", "nan", "None"):
                                item["leader_gap"] = format_delta(abs(time_val) if time_val.total_seconds() < 0 else time_val)
                            else:
                                total_time = (race_gap_meta.get(item["abbreviation"]) or {}).get("total_time")
                                if total_time is not None and leader_total is not None:
                                    delta = total_time - leader_total
                                    if hasattr(delta, "to_pytimedelta"):
                                        delta = delta.to_pytimedelta()
                                    item["leader_gap"] = format_delta(abs(delta) if isinstance(delta, timedelta) and delta.total_seconds() < 0 else delta)
                                else:
                                    item["leader_gap"] = ""

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


async def get_cached_last_completed_session_payload(calendar_data, target_season: int, expire: int = 900, timeout: float | None = None):
    cache = FastAPICache.get_backend()
    cache_key = f"f1:last_session:{target_season}"

    cached = await cache.get(cache_key)
    if cached:
        return cached

    try:
        if timeout is not None:
            response_data = await asyncio.wait_for(
                build_last_completed_session_payload(calendar_data, target_season),
                timeout=timeout,
            )
        else:
            response_data = await build_last_completed_session_payload(calendar_data, target_season)
    except asyncio.TimeoutError:
        response_data = {
            "season": calendar_data.get("season") or target_season,
            "message": "Last completed session is taking longer than expected to load.",
            "results": [],
            "result_count": 0,
            "load_error": "Timed out while loading the most recent completed session.",
        }

    response_data["cache_expires"] = (datetime.now(MT) + timedelta(seconds=expire)).isoformat()
    await cache.set(cache_key, response_data, expire=expire)
    return response_data


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

    last_completed_session = await get_cached_last_completed_session_payload(
        calendar_data,
        int(calendar_data.get("season") or get_target_season()),
        expire=900,
        timeout=8,
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
    timeline = build_weekend_timeline(next_race)

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
        "timeline": timeline,
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
    target_season = get_target_season()

    async with httpx.AsyncClient() as client:
        calendar_data = await fetch_calendar_data(client, target_season)
        if not calendar_data:
            return {"error": "Failed to fetch race schedule"}

    return await get_cached_last_completed_session_payload(
        calendar_data,
        target_season,
        expire=900,
        timeout=18,
    )
