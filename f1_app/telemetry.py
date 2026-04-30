import time
import math
import logging
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Any
from .config import OPENF1, JOLPICA, CURRENT_F1_YEAR, TEAM_ORDER_DEFAULT, OPENF1_SPEED_FETCH_TTL
from .http_client import safe_http_json, API_CACHE
from .utils import (
    normalize_driver_name, canonical_team_name, latest_by_key, 
    parse_iso_datetime, parse_qual_time, iso_utc
)
from .sessions import latest_race_session_backend, live_driver_team_map_for_session
from .constants import DRIVER_ID_MAP, DRIVER_TEAM_MAP, CIRCUIT_ID_MAP

logger = logging.getLogger('f1_app')

def build_live_speed_backend() -> dict[str, Any]:
    sess, is_live = latest_race_session_backend()
    if not sess or not sess.get("session_key"):
        return {"ok": False, "error": "No live or recent race session found"}

    sk = sess.get("session_key")
    now = datetime.now(timezone.utc)
    
    cache_key = f"speed-frame:{sk}"
    cached = API_CACHE.get(cache_key)
    if cached is not None:
        cached["cachedFrame"] = True
        return cached

    if not is_live:
        last = API_CACHE.get(f"last-speed-frame:{sk}")
        if last:
            last["cachedFrame"] = True
            return last
        return {"ok": False, "error": "No live race session active", "sessionKey": sk, "isLive": False}

    lookback = now - timedelta(seconds=4)
    anchor_q = urllib.parse.quote(iso_utc(lookback), safe="")
    url = f"{OPENF1}/car_data?session_key={sk}&date>={anchor_q}"

    rows = safe_http_json(url, timeout=4.0) or []
    if not rows:
        last = API_CACHE.get(f"last-speed-frame:{sk}")
        if last:
            last["cachedFrame"] = True
            last["source"] = "last-known-speed-frame"
            return last

    latest_by_driver = latest_by_key(rows, 'driver_number')
    speeds = []
    for dn, r in latest_by_driver.items():
        speed = r.get("speed")
        if speed is None: continue
        speeds.append({
            "driverNumber": dn,
            "speed": round(float(speed)),
            "rpm": int(float(r.get("rpm") or 0)),
            "gear": int(float(r.get("n_gear") or 0)),
            "throttle": int(float(r.get("throttle") or 0)),
            "brake": int(float(r.get("brake") or 0)),
            "date": r.get("date")
        })

    result = {
        "ok": True,
        "isLive": is_live,
        "sessionKey": sk,
        "source": "openf1-car-data",
        "generatedAt": time.time(),
        "cachedFrame": False,
        "speeds": speeds
    }
    API_CACHE.set(cache_key, result, ttl=OPENF1_SPEED_FETCH_TTL)
    API_CACHE.set(f"last-speed-frame:{sk}", result, ttl=30.0)
    return result

def build_live_pace_backend(payload: dict[str, Any]) -> dict[str, Any]:
    team_pace_prior = dict(payload.get('teamPace') or {})
    driver_skill_prior = dict(payload.get('driverSkill') or {})
    circuit_modifiers = dict(payload.get('circuitModifiers') or {})
    race_schedule = payload.get('raceSchedule') or []
    
    qual_json = safe_http_json(f'{JOLPICA}/{CURRENT_F1_YEAR}/qualifying.json?limit=500', timeout=7.0)
    races = (((qual_json or {}).get('MRData') or {}).get('RaceTable') or {}).get('Races') or []
    
    if not races:
        return {
            'ok': True,
            'teamPace': team_pace_prior,
            'driverSkill': driver_skill_prior,
            'circuitModifiers': circuit_modifiers,
            'paceLabelHtml': 'PACE RATINGS: <span style="color:var(--muted);">● HARDCODED PRIORS (no qualifying data yet)</span>',
            'updatedTeams': 0,
            'qualifyingCount': 0,
        }
        
    team_gaps: dict[str, list[float]] = {}
    for race in races:
        results = race.get('QualifyingResults') or []
        pole_time = None
        for r in results:
            t = parse_qual_time(r.get('Q3')) or parse_qual_time(r.get('Q2')) or parse_qual_time(r.get('Q1'))
            if t and (pole_time is None or t < pole_time):
                pole_time = t
        if pole_time is None:
            continue
        for r in results:
            driver = r.get('Driver') or {}
            team = DRIVER_TEAM_MAP.get(driver.get('driverId') or '')
            if not team:
                continue
            dt = parse_qual_time(r.get('Q3')) or parse_qual_time(r.get('Q2')) or parse_qual_time(r.get('Q1'))
            if not dt:
                continue
            gap_pct = (dt - pole_time) / pole_time
            team_gaps.setdefault(team, []).append(gap_pct)
            
    avg_gaps = {team: sum(gaps) / len(gaps) for team, gaps in team_gaps.items() if gaps}
    if avg_gaps:
        min_gap = min(avg_gaps.values())
        max_gap = max(avg_gaps.values())
        gap_range = max(max_gap - min_gap, 0.001)
        done = len(races)
        total = max(sum(1 for r in race_schedule if not r.get('canc')), 1)
        live_weight = math.sqrt(done / total)
        prior_weight = 1 - live_weight
        for team, avg_gap in avg_gaps.items():
            live_pace = 1.0 - ((avg_gap - min_gap) / gap_range) * 0.55
            prior = float(team_pace_prior.get(team, 0.55))
            team_pace_prior[team] = round(prior * prior_weight + live_pace * live_weight, 3)

    return {
        'ok': True,
        'teamPace': team_pace_prior,
        'driverSkill': driver_skill_prior,
        'circuitModifiers': circuit_modifiers,
        'paceLabelHtml': f'PACE RATINGS: <span style="color:var(--green);">● LIVE FROM {len(races)} QUALIFYING SESSIONS</span>',
        'updatedTeams': len(avg_gaps),
        'qualifyingCount': len(races),
    }

def build_live_pitstops_backend() -> dict[str, Any]:
    sessions = safe_http_json(f'{OPENF1}/sessions?year={CURRENT_F1_YEAR}&session_type=Race', timeout=8.0) or []
    fallback_label = 'PIT STOPS: <span style="color:var(--muted);">● HARDCODED PRIORS</span>'
    if not sessions:
        return {'ok': True, 'scores': {}, 'livePitstops': {}, 'avgTimes': {}, 'sessionCount': 0, 'labelHtml': fallback_label}
    
    # Sort and pick the latest one already started
    now = datetime.now(timezone.utc)
    sessions_started = [s for s in sessions if parse_iso_datetime(s.get('date_start')) and parse_iso_datetime(s.get('date_start')) <= now]
    sessions_started.sort(key=lambda s: parse_iso_datetime(s.get('date_start')), reverse=True)
    
    latest = sessions_started[0] if sessions_started else None
    latest_sk = latest.get('session_key') if latest else None
    if not latest_sk:
        return {'ok': True, 'scores': {}, 'livePitstops': {}, 'avgTimes': {}, 'sessionCount': 0, 'labelHtml': fallback_label}
        
    _, driver_team_map, _ = live_driver_team_map_for_session(latest_sk)
    team_pit_times: dict[str, list[float]] = {}
    used_sessions = 0
    
    for sess in sessions_started:
        sk = sess.get('session_key')
        if not sk: continue
        pit_stops = safe_http_json(f'{OPENF1}/pit?session_key={sk}', timeout=6.0) or []
        if pit_stops:
            used_sessions += 1
        for pit in pit_stops:
            duration = pit.get('pit_duration')
            driver_num = pit.get('driver_number')
            try:
                duration_f = float(duration)
            except Exception:
                continue
            if duration_f <= 0 or duration_f > 120:
                continue
            team = driver_team_map.get(driver_num) or ''
            team = canonical_team_name(team, TEAM_ORDER_DEFAULT)
            if not team:
                continue
            team_pit_times.setdefault(team, []).append(duration_f)
            
    if not team_pit_times:
        return {'ok': True, 'scores': {}, 'livePitstops': {}, 'avgTimes': {}, 'sessionCount': 0, 'labelHtml': fallback_label}
        
    avg_times: dict[str, float] = {}
    for team, times in team_pit_times.items():
        sorted_times = sorted(times)
        trimmed = sorted_times[: math.ceil(len(sorted_times) * 0.85)] if len(sorted_times) > 2 else sorted_times
        avg_times[team] = sum(trimmed) / max(len(trimmed), 1)
        
    fastest = min(avg_times.values())
    slowest = max(avg_times.values())
    spread = max(slowest - fastest, 0.1)
    
    scores: dict[str, int] = {}
    for team, avg in avg_times.items():
        score = round(95 - ((avg - fastest) / spread) * 30)
        scores[team] = max(min(score, 98), 60)
        
    return {
        'ok': True,
        'scores': scores,
        'livePitstops': scores,
        'avgTimes': {k: round(v, 3) for k, v in avg_times.items()},
        'sessionCount': used_sessions,
        'labelHtml': f'PIT STOPS: <span style="color:var(--green);">● LIVE FROM {used_sessions} RACE{"S" if used_sessions > 1 else ""}</span>',
    }
