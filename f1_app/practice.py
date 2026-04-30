from __future__ import annotations

import math
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Any

from .cache import API_CACHE
from .config import CURRENT_F1_YEAR, OPENF1, OPENF1_HEAVY_FETCH_TTL
from .http_client import safe_http_json
from .track_codes import get_track_code_from_session


def parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def is_practice_session(session: dict[str, Any]) -> bool:
    name = str(session.get("session_name") or "").lower()
    session_type = str(session.get("session_type") or "").lower()
    return (
        "practice" in name
        or "practice" in session_type
        or name in {"fp1", "fp2", "fp3"}
        or session_type in {"fp1", "fp2", "fp3"}
    )


def latest_practice_session_backend() -> tuple[dict[str, Any] | None, bool, str]:
    sessions = safe_http_json(
        f"{OPENF1}/sessions?year={CURRENT_F1_YEAR}",
        timeout=8.0,
        ttl=300.0,
    ) or []

    now = datetime.now(timezone.utc)
    practice_sessions = []
    live_sessions = []

    for s in sessions:
        if not is_practice_session(s):
            continue
        start = parse_iso_datetime(s.get("date_start"))
        end = parse_iso_datetime(s.get("date_end"))
        if not start:
            continue
        if start > now + timedelta(minutes=10):
            continue
        # Ignore sessions older than 7 days unless in historical mode
        if start < now - timedelta(days=7):
            continue
        practice_sessions.append(s)
        if end and start <= now <= end + timedelta(minutes=10):
            live_sessions.append(s)

    if live_sessions:
        live_sessions.sort(
            key=lambda x: parse_iso_datetime(x.get("date_start")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return live_sessions[0], True, "LIVE"

    if practice_sessions:
        practice_sessions.sort(
            key=lambda x: parse_iso_datetime(x.get("date_start")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return practice_sessions[0], False, "RECENT PRACTICE"

    return None, False, "NO PRACTICE"


def lap_time_to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
        if math.isfinite(v) and v > 0:
            return v
    except Exception:
        pass
    return None


def format_lap_seconds(value: Any) -> str:
    seconds = lap_time_to_float(value)
    if seconds is None:
        return "—"
    minutes = int(seconds // 60)
    rem = seconds - minutes * 60
    if minutes > 0:
        return f"{minutes}:{rem:06.3f}"
    return f"{seconds:.3f}"


def latest_by_driver(rows: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    latest: dict[Any, dict[str, Any]] = {}
    for row in rows or []:
        dn = row.get("driver_number")
        if dn is None:
            continue
        prev = latest.get(dn)
        if prev is None or str(row.get("date") or "") > str(prev.get("date") or ""):
            latest[dn] = row
    return latest


def best_and_last_lap_by_driver(laps: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    by_driver: dict[Any, dict[str, Any]] = {}
    for lap in laps or []:
        dn = lap.get("driver_number")
        if dn is None:
            continue
        try:
            lap_number = int(float(lap.get("lap_number") or 0))
        except Exception:
            lap_number = 0
        lap_duration = lap_time_to_float(lap.get("lap_duration"))
        info = by_driver.setdefault(dn, {
            "bestLap": None,
            "bestLapRaw": None,
            "bestLapNumber": None,
            "lastLap": None,
            "lastLapRaw": None,
            "lastLapNumber": None,
            "sector1": None,
            "sector2": None,
            "sector3": None,
        })
        if lap_number >= int(info.get("lastLapNumber") or 0):
            info["lastLap"] = format_lap_seconds(lap_duration)
            info["lastLapRaw"] = lap_duration
            info["lastLapNumber"] = lap_number
            info["sector1"] = format_lap_seconds(lap.get("duration_sector_1"))
            info["sector2"] = format_lap_seconds(lap.get("duration_sector_2"))
            info["sector3"] = format_lap_seconds(lap.get("duration_sector_3"))
        if lap_duration is not None:
            prev = info.get("bestLapRaw")
            if prev is None or lap_duration < float(prev):
                info["bestLap"] = format_lap_seconds(lap_duration)
                info["bestLapRaw"] = lap_duration
                info["bestLapNumber"] = lap_number
    return by_driver


def build_practice_live_timing_backend() -> dict[str, Any]:
    session, is_live, age_label = latest_practice_session_backend()

    if not session or not session.get("session_key"):
        return {
            "ok": True,
            "isLive": False,
            "error": None,
            "drivers": [],
            "meeting": "Race Weekend",
            "sessionName": "Practice",
            "sessionType": "Practice",
            "trackCode": "TRACK",
            "bestOverall": "—",
            "dataAgeLabel": age_label,
            "dataSourceLabel": "NO LIVE PRACTICE",
            "generatedAt": time.time(),
        }

    sk = session.get("session_key")
    track_code = get_track_code_from_session(session)

    cache_key = f"practice-live-timing:{sk}"
    cached = API_CACHE.get(cache_key)
    if cached is not None:
        cached["cachedFrame"] = True
        return cached

    now = datetime.now(timezone.utc)
    lookback = now - timedelta(minutes=20)
    anchor_q = urllib.parse.quote(iso_utc(lookback), safe="")

    drivers = safe_http_json(
        f"{OPENF1}/drivers?session_key={sk}",
        timeout=6.0,
        ttl=300.0,
    ) or []

    positions = safe_http_json(
        f"{OPENF1}/position?session_key={sk}",
        timeout=6.0,
        ttl=OPENF1_HEAVY_FETCH_TTL,
    ) or []

    laps = safe_http_json(
        f"{OPENF1}/laps?session_key={sk}",
        timeout=8.0,
        ttl=OPENF1_HEAVY_FETCH_TTL,
    ) or []

    car_data = safe_http_json(
        f"{OPENF1}/car_data?session_key={sk}&date>={anchor_q}",
        timeout=6.0,
        ttl=3.0,
    ) or []

    latest_pos = latest_by_driver(positions)
    latest_car = latest_by_driver(car_data)
    lap_info = best_and_last_lap_by_driver(laps)

    driver_map: dict[Any, dict[str, Any]] = {}
    for d in drivers:
        dn = d.get("driver_number")
        if dn is None:
            continue
        driver_map[dn] = {
            "driverNumber": dn,
            "name": d.get("full_name") or d.get("broadcast_name") or d.get("name_acronym") or f"Driver {dn}",
            "abbr": d.get("name_acronym") or str(dn),
            "team": d.get("team_name") or "Unknown",
            "teamColor": d.get("team_colour"),
            "headshot": d.get("headshot_url"),
        }

    best_overall: float | None = None
    for info in lap_info.values():
        raw = info.get("bestLapRaw")
        if raw is not None:
            if best_overall is None or float(raw) < float(best_overall):
                best_overall = float(raw)

    rows = []
    for dn, info in driver_map.items():
        pos = latest_pos.get(dn) or {}
        lap = lap_info.get(dn) or {}
        car = latest_car.get(dn) or {}
        best_raw = lap.get("bestLapRaw")
        gap_to_best = None
        if best_raw is not None and best_overall is not None:
            gap_to_best = float(best_raw) - float(best_overall)

        rows.append({
            "driverNumber": dn,
            "name": info["name"],
            "abbr": info["abbr"],
            "team": info["team"],
            "teamColor": info.get("teamColor"),
            "headshot": info.get("headshot"),
            "position": pos.get("position"),
            "bestLap": lap.get("bestLap") or "—",
            "bestLapRaw": best_raw,
            "bestLapNumber": lap.get("bestLapNumber"),
            "lastLap": lap.get("lastLap") or "—",
            "lastLapRaw": lap.get("lastLapRaw"),
            "lastLapNumber": lap.get("lastLapNumber"),
            "sector1": lap.get("sector1") or "—",
            "sector2": lap.get("sector2") or "—",
            "sector3": lap.get("sector3") or "—",
            "speed": car.get("speed"),
            "throttle": car.get("throttle"),
            "brake": car.get("brake"),
            "drs": car.get("drs"),
            "gapToBest": gap_to_best,
            "gapToBestText": "—" if gap_to_best is None else f"+{gap_to_best:.3f}",
            "dataTimestamp": car.get("date") or pos.get("date"),
        })

    rows.sort(key=lambda r: (
        r["bestLapRaw"] is None,
        float(r["bestLapRaw"] or 999999),
        int(float(r["position"] or 99)),
        str(r["name"]),
    ))

    for idx, row in enumerate(rows, start=1):
        row["practiceRank"] = idx

    result = {
        "ok": True,
        "isLive": is_live,
        "dataAgeLabel": age_label,
        "dataSourceLabel": "LIVE" if is_live else "RECENT PRACTICE",
        "sessionKey": sk,
        "trackCode": track_code,
        "meeting": session.get("meeting_name") or session.get("meeting_official_name") or session.get("location"),
        "sessionName": session.get("session_name") or "Practice",
        "sessionType": session.get("session_type") or "Practice",
        "dateStart": session.get("date_start"),
        "dateEnd": session.get("date_end"),
        "generatedAt": time.time(),
        "cachedFrame": False,
        "drivers": rows,
        "bestOverall": format_lap_seconds(best_overall),
    }

    API_CACHE.set(cache_key, result, ttl=5.0)
    return result
