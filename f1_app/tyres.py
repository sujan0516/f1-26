import time
import urllib.parse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional, Dict, List
from .config import (
    OPENF1,
    OPENF1_HEAVY_FETCH_TTL,
    DATA_DIR,
    PIT_LANE_LOSS,
    DEFAULT_PIT_LOSS_BY_TRACK,
    TYRE_BASE_LIFE,
    TRACK_WEAR_MULTIPLIER,
    TYRE_DEG_RATE,
)
from .http_client import safe_http_json
from .track_codes import normalize_track_code
from .sessions import latest_race_session_backend, infer_total_laps
from .utils import normalize_driver_name, canonical_team_name, latest_by_key, TEAM_ORDER_DEFAULT
from .weather import build_weather_backend

def get_deg_rate(compound: str) -> float:
    return TYRE_DEG_RATE.get(str(compound).upper(), 0.025)


def calculate_current_stint_age(stint: dict, current_lap: int) -> int:
    """Compute real current tyre age: age at stint start + laps completed in this stint."""
    try:
        age_at_start = int(float(stint.get("tyre_age_at_start") or 0))
    except Exception:
        age_at_start = 0
    try:
        lap_start = int(float(
            stint.get("lap_start")
            or stint.get("lap_start_number")
            or stint.get("stint_start_lap")
            or current_lap
        ))
    except Exception:
        lap_start = current_lap
    return max(0, age_at_start + max(0, int(current_lap) - lap_start))

def tyre_life_remaining(compound: str, age: int, track_wear: str) -> int:
    c = str(compound or "MEDIUM").upper()
    base_life = TYRE_BASE_LIFE.get(c, 30)
    wear_mult = TRACK_WEAR_MULTIPLIER.get(str(track_wear or "Medium"), 1.0)
    adjusted_life = max(1, round(base_life / wear_mult))
    return max(0, adjusted_life - max(0, int(age or 0)))

def tyre_degradation_penalty(compound: str, age: int, track_wear: str) -> float:
    c = str(compound or "MEDIUM").upper()
    rate = get_deg_rate(c)
    wear_mult = TRACK_WEAR_MULTIPLIER.get(str(track_wear or "Medium"), 1.0)
    return round(rate * max(0, int(age or 0)) * wear_mult, 3)

def choose_next_compound(current: str, rain_pct: int, age: int, track_wear: str) -> str:
    c = str(current or "MEDIUM").upper()
    if rain_pct >= 70: return "WET"
    if rain_pct >= 40: return "INTERMEDIATE"
    if c == "SOFT":
        return "MEDIUM" if str(track_wear) in {"High", "Extreme"} else "HARD"
    if c == "MEDIUM": return "HARD"
    if c == "HARD": return "MEDIUM" if age > 35 else "HARD"
    if c in {"INTERMEDIATE", "WET"}:
        return "INTERMEDIATE" if rain_pct >= 40 else "MEDIUM"
    return "MEDIUM"

def estimate_pit_window(compound: str, age: int, track_wear: str) -> Dict[str, Any]:
    remaining = tyre_life_remaining(compound, age, track_wear)
    if remaining <= 2: urgency = "BOX NOW"
    elif remaining <= 5: urgency = "PIT WINDOW OPEN"
    elif remaining <= 9: urgency = "PREPARE PIT WINDOW"
    else: urgency = "EXTEND STINT"
    return {
        "remainingLaps": remaining,
        "urgency": urgency,
        "recommendedInLaps": max(0, min(remaining - 2, 8)),
    }

def improved_undercut_model(
    gap_ahead: Optional[float],
    tyre_age: int,
    current_compound: str,
    new_compound: str,
    track_code: str,
    track_wear: str,
    traffic_risk: float = 0.0,
) -> Dict[str, Any]:
    pit_loss = DEFAULT_PIT_LOSS_BY_TRACK.get(track_code, PIT_LANE_LOSS)
    if gap_ahead is None:
        return {
            "viable": False,
            "status": "NO_GAP_DATA",
            "confidence": "LOW",
            "reason": "No reliable interval gap available.",
            "gapAhead": None,
            "targetGap": round(pit_loss, 2),
        }
    current_penalty = tyre_degradation_penalty(current_compound, tyre_age, track_wear)
    new_penalty = tyre_degradation_penalty(new_compound, 1, track_wear)
    tyre_delta_3_laps = max(0.0, (current_penalty - new_penalty) * 3.0)
    warmup_penalty = 0.6
    traffic_penalty = max(0.0, traffic_risk)
    target_gap = pit_loss - tyre_delta_3_laps + warmup_penalty + traffic_penalty
    viable = gap_ahead <= target_gap
    return {
        "viable": bool(viable),
        "status": "VIABLE" if viable else "NOT_VIABLE",
        "confidence": "MEDIUM",
        "gapAhead": round(gap_ahead, 2),
        "targetGap": round(target_gap, 2),
        "pitLoss": round(pit_loss, 2),
        "tyreDelta3Laps": round(tyre_delta_3_laps, 3),
        "warmupPenalty": warmup_penalty,
        "trafficPenalty": round(traffic_penalty, 2),
        "reason": (
            f"Gap {gap_ahead:.2f}s is inside undercut target {target_gap:.2f}s."
            if viable
            else f"Gap {gap_ahead:.2f}s is outside undercut target {target_gap:.2f}s."
        ),
    }

def undercut_status_label(undercut: Dict[str, Any]) -> str:
    if not undercut: return 'NO_GAP_DATA'
    if undercut.get('viable'): return 'VIABLE'
    if undercut.get('gapAhead') is None: return 'NO_GAP_DATA'
    return 'NOT_VIABLE'


def normalize_track_wear(value: Any) -> str:
    text = str(value or "Medium")
    first = text.split("—", 1)[0].split("-", 1)[0].strip()
    if first in {"Low", "Medium", "High", "Extreme"}:
        return first
    return "Medium"


def load_bootstrap_data() -> dict[str, Any]:
    try:
        return json.loads((Path(DATA_DIR) / "bootstrap_data.json").read_text())
    except Exception:
        return {}


def build_team_summary(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    teams: dict[str, dict[str, Any]] = {}
    for row in recommendations:
        team = row.get("team") or "Unknown"
        item = teams.setdefault(team, {"team": team, "boxNow": 0, "undercutCount": 0, "drivers": 0})
        item["drivers"] += 1
        if str((row.get("pitWindow") or {}).get("urgency") or "").upper() == "BOX NOW":
            item["boxNow"] += 1
        if (row.get("undercut") or {}).get("viable"):
            item["undercutCount"] += 1
    return sorted(teams.values(), key=lambda x: (-x["boxNow"], -x["undercutCount"], x["team"]))


def current_driver_team(stats: dict[str, Any]) -> str:
    if stats.get("team"):
        return str(stats.get("team"))
    seasons = stats.get("seasons") or []
    for season in seasons:
        try:
            if int(season.get("year") or 0) == 2026 and season.get("team"):
                return str(season.get("team"))
        except Exception:
            continue
    if seasons and isinstance(seasons[0], dict) and seasons[0].get("team"):
        return str(seasons[0].get("team"))
    return "Unknown"


def build_projected_tyre_strategy_backend(track_code: str = "MIA", simulate_rain: bool = False) -> Dict[str, Any]:
    track_code = normalize_track_code(track_code or "MIA")
    boot = load_bootstrap_data()
    track = (boot.get("TRACK_DB") or {}).get(track_code) or {}
    drivers_db = boot.get("DRIVER_DB") or {}
    track_wear = normalize_track_wear(track.get("tyreWear"))
    total_laps = int(track.get("laps") or infer_total_laps(track_code))

    weather = build_weather_backend(track_code).get("weather") or {}
    rain_pct = 85 if simulate_rain else round(float(weather.get("rainChance") or 0.0) * 100)
    is_wet = rain_pct >= 70
    is_mixed = 40 <= rain_pct < 70
    mode = "PROJECTED STRATEGY (WET)" if is_wet else "PROJECTED STRATEGY (MIXED)" if is_mixed else "PROJECTED STRATEGY"
    mode_color = "#5aafff" if is_wet else "var(--gold)" if is_mixed else "var(--green)"
    default_c = "WET" if is_wet else "INTERMEDIATE" if is_mixed else ("MEDIUM" if track_wear in {"High", "Extreme"} else "SOFT")

    recommendations: list[dict[str, Any]] = []
    for name, stats in drivers_db.items():
        team = canonical_team_name(current_driver_team(stats), TEAM_ORDER_DEFAULT)
        age = 0
        next_c = choose_next_compound(default_c, rain_pct, age, track_wear)
        pit_window = estimate_pit_window(default_c, age, track_wear)
        pit_window["urgency"] = "PROJECTED"
        pit_window["recommendedInLaps"] = 16 if track_wear in {"High", "Extreme"} else 22
        undercut = {
            "viable": False,
            "status": "PROJECTED",
            "confidence": "LOW",
            "reason": "Waiting for live interval data.",
            "gapAhead": None,
            "targetGap": round(DEFAULT_PIT_LOSS_BY_TRACK.get(track_code, PIT_LANE_LOSS), 2),
            "pitLoss": round(DEFAULT_PIT_LOSS_BY_TRACK.get(track_code, PIT_LANE_LOSS), 2),
        }
        recommendations.append({
            "driverNumber": stats.get("number"),
            "name": name,
            "team": team,
            "teamColor": stats.get("teamColor"),
            "compound": default_c,
            "tyreAge": age,
            "lifeRemaining": tyre_life_remaining(default_c, age, track_wear),
            "degradationPenalty": tyre_degradation_penalty(default_c, age, track_wear),
            "recommendedCompound": next_c,
            "posture": "PROJECTED BASELINE",
            "pitWindow": pit_window,
            "undercut": undercut,
            "undercutStatus": undercut_status_label(undercut),
            "gapAhead": None,
            "alerts": ["PROJECTED DATA - LIVE STINTS NOT AVAILABLE"],
            "summary": "Projected race strategy based on track wear, baseline compound life, and race-day weather estimate.",
        })

    return {
        "ok": True,
        "isLive": False,
        "isProjected": True,
        "isPredicted": True,
        "sessionKey": None,
        "trackCode": track_code,
        "currentLap": 1,
        "totalLaps": total_laps,
        "trackWear": track_wear,
        "rainPct": rain_pct,
        "mode": mode,
        "modeColor": mode_color,
        "dataSourceLabel": "PROJECTED",
        "safetyCarWindow": False,
        "generatedAt": time.time(),
        "recommendations": recommendations,
        "teamSummary": build_team_summary(recommendations),
        "dataQuality": {
            "mode": "PROJECTED",
            "confidence": "LOW",
            "hasStints": False,
            "hasIntervals": False,
            "hasLaps": False,
            "hasWeather": bool(weather),
        },
    }

def build_tyre_strategy_backend(track_code: str = "MIA", simulate_rain: bool = False) -> Dict[str, Any]:
    track_code = normalize_track_code(track_code or "MIA")
    sess, is_live = latest_race_session_backend()
    if not sess or not sess.get('session_key') or not is_live:
        return build_projected_tyre_strategy_backend(track_code=track_code, simulate_rain=simulate_rain)
    sk = sess.get('session_key')
    now = datetime.now(timezone.utc)
    lookback = now - timedelta(minutes=10)
    anchor_q = urllib.parse.quote(lookback.isoformat().replace('+00:00', 'Z'), safe='')
    drivers = safe_http_json(f'{OPENF1}/drivers?session_key={sk}', timeout=5.0, ttl=300.0) or []
    stints = safe_http_json(f'{OPENF1}/stints?session_key={sk}', timeout=5.0, ttl=OPENF1_HEAVY_FETCH_TTL) or []
    intervals = safe_http_json(f'{OPENF1}/intervals?session_key={sk}&date>={anchor_q}', timeout=5.0, ttl=OPENF1_HEAVY_FETCH_TTL) or []
    laps = safe_http_json(f'{OPENF1}/laps?session_key={sk}&date>={anchor_q}', timeout=5.0, ttl=OPENF1_HEAVY_FETCH_TTL) or []
    driver_map = {}
    for d in drivers:
        dn = d.get('driver_number')
        if dn is None: continue
        driver_map[dn] = {
            'driverNumber': dn,
            'name': normalize_driver_name(d.get('full_name') or d.get('name_acronym') or f'#{dn}'),
            'team': canonical_team_name(d.get('team_name') or '', TEAM_ORDER_DEFAULT),
        }
    latest_stint = {}
    for s in stints:
        dn = s.get('driver_number')
        if dn is None: continue
        prev = latest_stint.get(dn)
        if prev is None or int(s.get('stint_number') or 0) > int(prev.get('stint_number') or 0):
            latest_stint[dn] = s
    interval_map = latest_by_key(intervals, 'driver_number')
    latest_lap_by_driver = latest_by_key(laps, 'driver_number')
    boot = load_bootstrap_data()
    track = (boot.get("TRACK_DB") or {}).get(track_code) or {}
    weather = build_weather_backend(track_code).get("weather") or {}
    rain_pct = 85 if simulate_rain else round(float(weather.get("rainChance") or 0.0) * 100)
    track_wear = normalize_track_wear(track.get("tyreWear"))
    current_lap = 1
    for lap in latest_lap_by_driver.values():
        try:
            current_lap = max(current_lap, int(float(lap.get('lap_number') or 1)))
        except Exception:
            pass
    recommendations = []
    for dn, info in driver_map.items():
        stint = latest_stint.get(dn) or {}
        interval = interval_map.get(dn) or {}
        compound = str(stint.get('compound') or 'MEDIUM').upper()
        # Determine current lap for this driver
        driver_latest_lap = latest_lap_by_driver.get(dn) or {}
        try:
            current_lap_for_driver = int(float(driver_latest_lap.get('lap_number') or 1))
        except Exception:
            current_lap_for_driver = 1
        # Use real current tyre age (not just age at stint start)
        stint_age = calculate_current_stint_age(stint, current_lap_for_driver)
        gap_ahead = interval.get('gap_to_car_ahead')
        if isinstance(gap_ahead, str) and gap_ahead.lower() == 'leader': gap_ahead = 0.0
        try: gap_ahead = float(str(gap_ahead).replace('+', '').strip())
        except: gap_ahead = None
        next_c = choose_next_compound(compound, rain_pct, stint_age, track_wear)
        pit_win = estimate_pit_window(compound, stint_age, track_wear)
        undercut = improved_undercut_model(gap_ahead, stint_age, compound, next_c, track_code, track_wear)
        recommendations.append({
            'driverNumber': dn,
            'name': info['name'],
            'team': info['team'],
            'compound': compound,
            'tyreAge': stint_age,
            'lifeRemaining': tyre_life_remaining(compound, stint_age, track_wear),
            'degradationPenalty': tyre_degradation_penalty(compound, stint_age, track_wear),
            'recommendedCompound': next_c,
            'posture': 'LIVE STRATEGY',
            'pitWindow': pit_win,
            'undercut': undercut,
            'undercutStatus': undercut_status_label(undercut),
            'gapAhead': gap_ahead,
            'alerts': [],
            'summary': f"Live stint on {compound}. {pit_win.get('urgency')} based on tyre life and current lap data.",
        })
    return {
        "ok": True,
        "isLive": is_live,
        "isProjected": False,
        "sessionKey": sk,
        "trackCode": track_code,
        "currentLap": current_lap,
        "totalLaps": infer_total_laps(track_code),
        "trackWear": track_wear,
        "rainPct": rain_pct,
        "mode": "LIVE" if is_live else "RECENT",
        "dataSourceLabel": "LIVE" if is_live else "RECENT",
        "safetyCarWindow": False,
        "generatedAt": time.time(),
        "recommendations": recommendations,
        "teamSummary": build_team_summary(recommendations),
        "dataQuality": {
            "mode": "LIVE" if is_live else "RECENT",
            "confidence": "HIGH" if is_live else "MEDIUM",
            "hasStints": bool(stints),
            "hasIntervals": bool(intervals),
            "hasLaps": bool(laps),
            "hasWeather": False,
        },
    }
