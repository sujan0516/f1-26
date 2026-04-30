from __future__ import annotations

from flask import Blueprint, request, jsonify

from typing import Any, Optional, Dict, List

import json, math, random, time

from datetime import datetime, timedelta, timezone

import html

import numpy as np

from pathlib import Path

from .config import DATA_DIR, CURRENT_F1_YEAR, DRIVER_HEADSHOT_OVERRIDES, OPENF1, JOLPICA, TEAM_ORDER_DEFAULT, TYRE_DEG_RATE

from .http_client import safe_http_json

from .cache import API_CACHE

from .sessions import latest_race_session_backend, live_driver_team_map_for_session

from .constants import TYRE_PACE_DEFAULT, TYRE_COLORS_DEFAULT, CIRCUIT_OVERTAKE_DEFAULT

from .utils import canonical_team_name, get_tc, get_team_logo, normalize_driver_standings, normalize_constructors_standings, parse_iso_datetime, normalize_driver_name

from .weather import build_weather_backend


legacy_api = Blueprint('legacy', __name__)


DYNAMIC_BIOS_PATH = Path(DATA_DIR) / 'dynamic_bios.json'


CIRCUIT_TECH_BRIEFS = {
    'BAH': {'brake': 'High', 'aero': 'Medium-Low', 'overtake': 'High', 'stress': 'Thermal'},
    'SAU': {'brake': 'Medium', 'aero': 'Low', 'overtake': 'Medium', 'stress': 'G-Force'},
    'AUS': {'brake': 'High', 'aero': 'Medium', 'overtake': 'Medium', 'stress': 'Engine'},
    'JPN': {'brake': 'Low', 'aero': 'High', 'overtake': 'Low', 'stress': 'Tyre Lateral'},
    'CHN': {'brake': 'High', 'aero': 'Medium', 'overtake': 'High', 'stress': 'Front-Left'},
    'MIA': {'brake': 'High', 'aero': 'Medium-Low', 'overtake': 'Medium', 'stress': 'Heat'},
    'EMI': {'brake': 'High', 'aero': 'High', 'overtake': 'Low', 'stress': 'Kerbs'},
    'MON': {'brake': 'Extreme', 'aero': 'Max', 'overtake': 'Impossible', 'stress': 'Driver'},
    'ESP': {'brake': 'Medium', 'aero': 'High', 'overtake': 'Low', 'stress': 'Tyre wear'},
    'CAN': {'brake': 'Extreme', 'aero': 'Low', 'overtake': 'High', 'stress': 'Kerbs'},
    'AUT': {'brake': 'High', 'aero': 'Medium-Low', 'overtake': 'High', 'stress': 'Engine'},
    'GBR': {'brake': 'Low', 'aero': 'High', 'overtake': 'Medium', 'stress': 'Suspension'},
    'HUN': {'brake': 'High', 'aero': 'Max', 'overtake': 'Low', 'stress': 'Thermal'},
    'BEL': {'brake': 'Medium', 'aero': 'Low', 'overtake': 'High', 'stress': 'Compression'},
    'NED': {'brake': 'Medium', 'aero': 'High', 'overtake': 'Low', 'stress': 'Banked loads'},
    'ITA': {'brake': 'Extreme', 'aero': 'Min', 'overtake': 'High', 'stress': 'Engine'},
    'AZE': {'brake': 'Extreme', 'aero': 'Min', 'overtake': 'High', 'stress': 'Hybrid system'},
    'SIN': {'brake': 'Extreme', 'aero': 'Max', 'overtake': 'Low', 'stress': 'Humidity'},
    'USA': {'brake': 'High', 'aero': 'Medium', 'overtake': 'High', 'stress': 'Bumps'},
    'MEX': {'brake': 'Extreme', 'aero': 'Max', 'overtake': 'Medium', 'stress': 'Altitude'},
    'BRA': {'brake': 'High', 'aero': 'Medium', 'overtake': 'High', 'stress': 'Engine'},
    'LVG': {'brake': 'Extreme', 'aero': 'Min', 'overtake': 'High', 'stress': 'Cold tyres'},
    'QAT': {'brake': 'Low', 'aero': 'High', 'overtake': 'Low', 'stress': 'Dust'},
    'ABU': {'brake': 'High', 'aero': 'Medium', 'overtake': 'Medium', 'stress': 'Brake cooling'}
}

def get_deg_rate(compound: str) -> float:
    return TYRE_DEG_RATE.get(str(compound).upper(), 0.025)

@legacy_api.get('/api/circuit-brief')
def api_circuit_brief() -> Any:
    name = request.args.get('name', 'BAH')
    brief = CIRCUIT_TECH_BRIEFS.get(name, CIRCUIT_TECH_BRIEFS.get('BAH'))
    return jsonify({'ok': True, 'brief': brief})

def calculate_driver_radar(driver_name: str) -> dict[str, int]:
    """Generates professional performance scores (0-100) based on 2026 form and traits."""
    # Deterministic noise based on name for trait variety
    h = sum(ord(c) for c in driver_name)
    
    # Base trait modifiers (subjective professional assessment)
    TRAITS = {
        'Max Verstappen': {'pace': 98, 'craft': 95, 'cons': 96, 'tyre': 92, 'def': 94},
        'Lewis Hamilton': {'pace': 95, 'craft': 98, 'cons': 94, 'tyre': 97, 'def': 93},
        'Charles Leclerc': {'pace': 99, 'craft': 92, 'cons': 90, 'tyre': 88, 'def': 90},
        'Lando Norris': {'pace': 94, 'craft': 93, 'cons': 95, 'tyre': 94, 'def': 92},
        'George Russell': {'pace': 96, 'craft': 90, 'cons': 92, 'tyre': 90, 'def': 91},
        'Kimi Antonelli': {'pace': 97, 'craft': 88, 'cons': 85, 'tyre': 84, 'def': 86},
    }
    
    base = TRAITS.get(driver_name, {
        'pace': 85 + (h % 10),
        'craft': 82 + ((h*7) % 12),
        'cons': 80 + ((h*3) % 15),
        'tyre': 78 + ((h*2) % 18),
        'def': 80 + ((h*5) % 14)
    })
    
    # Adjust slightly based on 2026 team points for "live form"
    # (Simplified for now, in a real app would use the standing DB)
    return base

@legacy_api.get('/api/driver-radar')
def api_driver_radar() -> Any:
    d1 = request.args.get('d1', '')
    d2 = request.args.get('d2', '')
    return jsonify({
        'ok': True,
        'radar1': calculate_driver_radar(d1),
        'radar2': calculate_driver_radar(d2) if d2 else None
    })

def find_constructor_entry(team_name: str, constructors: list[dict[str, Any]], team_order: list[str]) -> dict[str, Any] | None:
    target = canonical_team_name(team_name, team_order)
    for c in constructors or []:
        if canonical_team_name(c.get('name') or c.get('team_name') or '', team_order) == target:
            return c
    return None

def team_drivers_for(team_name: str, drivers: list[dict[str, Any]], team_order: list[str]) -> list[dict[str, Any]]:
    target = canonical_team_name(team_name, team_order)
    return [d for d in drivers or [] if canonical_team_name(d.get('team') or d.get('team_name') or '', team_order) == target]

def _box_muller_normal(shape: tuple[int, ...], rng: np.random.Generator) -> np.ndarray:
    """Box-Muller transform: produces exact standard normal samples from two
    independent uniform draws.  Shape must be 2-D; returns same shape array."""
    u1 = rng.uniform(1e-10, 1.0, shape)  # avoid log(0)
    u2 = rng.uniform(0.0, 1.0, shape)
    return np.sqrt(-2.0 * np.log(u1)) * np.cos(2.0 * np.pi * u2)

def build_pace_model(
    drivers: list[dict[str, Any]],
    race_schedule: list[dict[str, Any]],
    team_pace: dict[str, float],
    driver_skill: dict[str, float],
) -> np.ndarray:
    """Returns a normalised numpy array of per-driver race-pace weights.

    Uses a Bayesian evidence-weighted blend:
      * Prior  = skill × team-pace composite
      * Update = sqrt-damped points-per-race form
    Evidence weight rises smoothly (smoothstep) from 0 → 1 as the season
    progresses, so early races bias towards the prior and late-season
    observations dominate.
    """
    done = max(sum(1 for r in race_schedule if r.get('done')), 1)
    total = max(sum(1 for r in race_schedule if not r.get('canc')), 1)

    skill = np.array([float(driver_skill.get(d.get('name'), 0.70)) for d in drivers])
    team  = np.array([float(team_pace.get(d.get('team'), 0.55)) for d in drivers])
    form_raw = np.array([max(float(d.get('pts', 0)) / done, 0.5) / 25.0 for d in drivers])

    # Smoothstep evidence weight — rises cubically, suppresses early noise.
    t = done / total
    evidence_weight = t * t * (3.0 - 2.0 * t)

    raw_prior = 0.65 + (skill * team - 0.35) * 0.6
    prior = raw_prior / (raw_prior.sum() or 1.0)

    flat_form = np.sqrt(form_raw)
    form = flat_form / (flat_form.sum() or 1.0)

    blended = prior * (1.0 - evidence_weight) + form * evidence_weight
    return blended / (blended.sum() or 1.0)

def generate_team_insights(drivers: list[dict[str, Any]], constructors: list[dict[str, Any]], race_schedule: list[dict[str, Any]], reliability: dict[str, float], team_pace: dict[str, float], live_pitstops: dict[str, float], team_metrics: dict[str, dict[str, Any]], team_order: list[str]) -> dict[str, dict[str, Any]]:
    done = max(sum(1 for r in race_schedule if r.get('done')), 1)
    engineering = {}
    for team_name in team_order:
        metrics = dict(team_metrics.get(team_name) or {})
        live = find_constructor_entry(team_name, constructors, team_order) or {'pts': 0, 'pos': 11, 'name': team_name}
        pace = float(team_pace.get(team_name, 0.50))
        team_drivers = team_drivers_for(team_name, drivers, team_order)
        team_pts = int(live.get('pts', 0))
        pts_per_race = f"{(team_pts / done):.1f}" if done > 0 else '0'
        avg_rel = sum(float(reliability.get(d.get('name'), 0.93)) for d in team_drivers) / max(len(team_drivers), 1) if team_drivers else 0.93
        pit_score = int(round(float(live_pitstops.get(team_name) or metrics.get('pitstop') or 78)))
        strengths = []
        if int(live.get('pos', 11)) <= 3:
            strengths.append(f"P{live.get('pos')} in constructors — {team_pts} points from {done} race{'s' if done > 1 else ''}")
        if pace >= 0.90:
            strengths.append(f"Top-tier car pace ({round(pace * 100)}/100)")
        if avg_rel >= 0.95:
            strengths.append(f"Excellent reliability ({round(avg_rel * 100)}%)")
        if pit_score >= 88:
            strengths.append(f"Elite pit stop execution ({pit_score}/100)")
        if float(pts_per_race) >= 20:
            strengths.append(f"{pts_per_race} points per race — championship pace")
        for d in team_drivers:
            if int(d.get('pts', 0)) >= team_pts * 0.6 and int(d.get('pts', 0)) > 10:
                strengths.append(f"{str(d.get('name', '')).split(' ')[-1]} carrying the team with {d.get('pts', 0)} points")
        if int(live.get('pos', 11)) <= 5 and pace < 0.75:
            strengths.append('Overperforming vs car pace — extracting maximum')
        if not strengths:
            strengths.append('Competitive midfield package')
        weaknesses = []
        if avg_rel < 0.88:
            weaknesses.append(f"Reliability concern — {round((1 - avg_rel) * 100)}% DNF rate")
        if pit_score < 78:
            weaknesses.append(f"Pit stops below average ({pit_score}/100)")
        if int(live.get('pos', 11)) > 7 and pace > 0.60:
            weaknesses.append(f"P{live.get('pos')} in standings — underperforming vs car potential")
        if pace < 0.55:
            weaknesses.append(f"Lowest car pace in the field ({round(pace * 100)}/100)")
        leader = constructors[0] if constructors else None
        if leader and int(leader.get('pts', 0)) - team_pts > 50:
            weaknesses.append(f"{int(leader.get('pts', 0)) - team_pts} points behind {leader.get('name') or 'P1'}")
        for d in team_drivers:
            if int(d.get('pts', 0)) == 0 and done >= 2:
                weaknesses.append(f"{str(d.get('name', '')).split(' ')[-1]} yet to score in {done} races")
        if not weaknesses:
            weaknesses.append('No major weaknesses identified')
        improvements = []
        if avg_rel < 0.90:
            improvements.append({'tag': 'engine', 'advice': f"Reliability at {round(avg_rel * 100)}% needs immediate attention — target {round(min(avg_rel + 0.05, 0.98) * 100)}% by mid-season through PU conservation modes."})
        if pit_score < 82:
            improvements.append({'tag': 'pit', 'advice': f"Pit stops averaging {pit_score}/100 — dedicated pit crew drills and equipment audit needed before next race."})
        if pace < 0.70 and int(live.get('pos', 11)) > 6:
            improvements.append({'tag': 'aero', 'advice': f"Car pace deficit significant ({round(pace * 100)}/100) — prioritise aerodynamic development, consider bold setup experiments at upcoming races."})
        if float(pts_per_race) < 5 and pace > 0.55:
            improvements.append({'tag': 'strat', 'advice': f"Only {pts_per_race} pts/race despite decent pace — review race strategy and qualifying preparation for missed opportunities."})
        if not improvements:
            improvements.append({'tag': 'strat', 'advice': f"Maintain current trajectory — {pts_per_race} pts/race is on target. Focus on consistency and development for second half of season."})
        metrics['strengths'] = strengths
        metrics['weaknesses'] = weaknesses
        metrics['improvements'] = improvements
        engineering[team_name] = metrics
    return engineering

def build_team_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    live_drivers = payload.get('liveDrivers') or []
    live_constructors = payload.get('liveConstructors') or []
    fallback_drivers = payload.get('fallbackDrivers') or []
    fallback_constructors = payload.get('fallbackConstructors') or []
    race_schedule = payload.get('raceSchedule') or []
    latest_mc = payload.get('latestMonteCarloResult') or {}
    reliability = payload.get('reliability') or {}
    team_pace = payload.get('teamPace') or {}
    live_pitstops = payload.get('livePitstops') or {}
    team_metrics = payload.get('teamMetrics') or {}
    team_order = payload.get('teamOrder') or []
    constructors = normalize_constructors_standings(live_constructors or fallback_constructors, team_order)
    drivers = normalize_driver_standings(live_drivers or fallback_drivers, team_order)
    engineering = generate_team_insights(drivers, constructors, race_schedule, reliability, team_pace, live_pitstops, team_metrics, team_order)
    done = max(sum(1 for r in race_schedule if r.get('done')), 1)
    total = max(sum(1 for r in race_schedule if not r.get('canc')), done)
    remaining = max(total - done, 0)
    mc_projection = {}
    for name, pts in (latest_mc.get('constructorMedianPts') or {}).items():
        key = canonical_team_name(name, team_order)
        if not key:
            continue
        val = int(round(float(pts or 0)))
        mc_projection[key] = max(mc_projection.get(key, 0), val)
    has_mc = bool(mc_projection)
    teams = []
    for team_name in team_order:
        eng = engineering.get(team_name, {})
        live = find_constructor_entry(team_name, constructors, team_order) or {'name': team_name, 'pts': 0, 'pos': 11}
        pace_model = float(team_pace.get(team_name, (eng.get('pace', 50) / 100)))
        pace_score = round(pace_model * 100)
        team_drivers = team_drivers_for(team_name, drivers, team_order)
        team_pts = int(live.get('pts', 0))
        pts_per_race_num = team_pts / done if done > 0 else 0.0
        pts_per_race = f"{pts_per_race_num:.1f}" if done > 0 else '—'
        reliability_using_fallback = not bool(team_drivers)
        avg_rel = sum(float(reliability.get(d.get('name'), 0.93)) for d in team_drivers) / max(len(team_drivers), 1) if team_drivers else (float(eng.get('reliability', 93)) / 100)
        rel_score = round(avg_rel * 100)
        pitstop_using_fallback = not (float(live_pitstops.get(team_name, 0)) > 0)
        pit_stop = round(float(live_pitstops.get(team_name) or eng.get('pitstop') or (team_metrics.get(team_name) or {}).get('pitstop') or 78))
        driver_count = min(len(team_drivers) or 2, 2)
        estimated_pts_per_race = pace_model * 0.55 * 25 * avg_rel * driver_count
        race_fraction = min(done / total, 1) if total else 0
        evidence_w = race_fraction * race_fraction * (3 - 2 * race_fraction)
        live_pts_per_race = pts_per_race_num if done > 0 else estimated_pts_per_race
        blended_rate = estimated_pts_per_race * (1 - evidence_w) + live_pts_per_race * evidence_w
        heuristic_projected = round(team_pts + blended_rate * remaining)
        projected = mc_projection.get(team_name, heuristic_projected) if has_mc else heuristic_projected
        projection_source = 'MONTE CARLO' if (has_mc and team_name in mc_projection) else 'HEURISTIC FALLBACK'
        leader = constructors[0] if constructors else None
        gap = max(0, int(leader.get('pts', 0)) - team_pts) if leader and canonical_team_name(leader.get('name'), team_order) != canonical_team_name(team_name, team_order) else 0
        gap_str = f"-{gap} pts from P1" if gap > 0 else 'CHAMPIONSHIP LEADER'
        overperforming = int(live.get('pos', 11)) <= 3 and pace_model < 0.80
        underperforming = int(live.get('pos', 11)) > 5 and pace_model > 0.80
        current_strength = 'Overperforming vs car pace — extracting maximum' if overperforming else 'Underperforming vs car potential — issues limiting results' if underperforming else (eng.get('strengths') or ['Competitive package'])[0]
        team_subtitle = f"P{live.get('pos', 11)} in constructors — {team_pts} points from {done} race{'s' if done > 1 else ''}"
        team_drivers_sorted = sorted(team_drivers, key=lambda d: int(d.get('pts', 0)), reverse=True)
        lead_driver = team_drivers_sorted[0] if team_drivers_sorted else None
        driver_line = ' · '.join(f"{d.get('name')} ({d.get('pts', 0)})" for d in team_drivers_sorted) if team_drivers_sorted else 'Driver data unavailable'
        source_notes = []
        if not live_constructors:
            source_notes.append('Constructor points are cached fallback data')
        if not live_drivers:
            source_notes.append('Driver points are cached fallback data')
        if pitstop_using_fallback:
            source_notes.append('Pit stop score is using fallback priors')
        if reliability_using_fallback:
            source_notes.append('Reliability is estimated from fallback priors')
        if projection_source != 'MONTE CARLO':
            source_notes.append('Projected final points are using the heuristic fallback because the constructors simulation has not been run yet')
        teams.append({
            'name': team_name,
            'col': get_tc(team_name),
            'live': {'name': live.get('name', team_name), 'pts': team_pts, 'pos': int(live.get('pos', 11))},
            'pace': pace_model,
            'paceScore': pace_score,
            'relScore': rel_score,
            'pitStop': pit_stop,
            'ptsPerRace': pts_per_race,
            'projected': int(projected),
            'projectionSource': projection_source,
            'gap': gap_str,
            'pu': eng.get('pu', '—'),
            'chassis': eng.get('chassis', '—'),
            'currentStrength': current_strength,
            'teamSubtitle': team_subtitle,
            'leadDriver': lead_driver,
            'driverLine': driver_line,
            'criticalWeakness': (eng.get('weaknesses') or ['No critical weakness flagged'])[0],
            'improvements': eng.get('improvements') or [],
            'strengths': (eng.get('strengths') or [])[:4],
            'weaknesses': (eng.get('weaknesses') or [])[:4],
            'sourceNotes': source_notes,
            'showingFallback': bool(source_notes),
        })
    return {
        'sourceLabel': 'LIVE' if (live_constructors and live_drivers) else 'HARDCODED FALLBACK',
        'projectionLabel': 'MONTE CARLO' if has_mc else 'HEURISTIC FALLBACK',
        'showingFallbackSummary': not (live_constructors and live_drivers),
        'teams': teams,
    }

def transcribe_audio_url(url: str, force: bool = False) -> dict[str, Any]:
    key = str(url or '').strip()
    if not key:
        return {'ok': False, 'error': 'Missing recording URL.'}
    if not force:
        cached = TRANSCRIPT_CACHE.get(key)
        if cached is not None:
            cached_copy = dict(cached)
            cached_copy['cached'] = True
            return cached_copy
    try:
        audio_bytes, headers, final_url = http_bytes(key, timeout=20.0)
    except Exception as exc:
        return {'ok': False, 'error': f'Could not download radio audio: {exc}'}
    if not audio_bytes:
        return {'ok': False, 'error': 'Downloaded radio audio was empty.'}
    filename = guess_audio_filename(final_url, headers)
    content_type = str(headers.get('content-type') or 'audio/mpeg').split(';')[0].strip() or 'audio/mpeg'
    result = transcribe_audio_locally(audio_bytes, filename, content_type=content_type)
    if result.get('ok'):
        payload = {
            'ok': True,
            'text': str(result.get('text') or '').strip(),
            'source': result.get('source') or 'openai',
            'cached': False,
            'audioUrl': final_url,
            'filename': filename,
        }
        TRANSCRIPT_CACHE.set(key, payload)
        return payload
    return result

def latest_session_from_list(sessions: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any] | None:
    if not sessions:
        return None
    now = now or datetime.now(timezone.utc)

    def dt_for(s: dict[str, Any], *keys: str) -> datetime:
        for key in keys:
            dt = parse_iso_datetime(s.get(key))
            if dt:
                return dt
        return datetime.min.replace(tzinfo=timezone.utc)

    enriched: list[tuple[dict[str, Any], datetime, datetime]] = []
    for s in sessions:
        start = dt_for(s, 'date_start', 'date', 'date_end')
        end = dt_for(s, 'date_end', 'date_start', 'date')
        enriched.append((s, start, end))

    live = [item for item in enriched if item[1] <= now <= item[2]]
    if live:
        live.sort(key=lambda item: (item[1], item[2]))
        return live[-1][0]

    started = [item for item in enriched if item[1] <= now]
    if started:
        started.sort(key=lambda item: (item[1], item[2]))
        return started[-1][0]

    enriched.sort(key=lambda item: (item[1], item[2]))
    return enriched[0][0]

def build_telemetry_h2h_backend(d1: str, d2: str) -> dict[str, Any]:
    """Fetch synchronized telemetry for two drivers (OpenF1)."""
    sessions = safe_http_json(f'{OPENF1}/sessions?year={CURRENT_F1_YEAR}&session_type=Race', timeout=8.0) or []
    latest = latest_session_from_list(sessions)
    if not latest: return {'ok': False, 'error': 'No session'}
    sk = latest.get('session_key')
    now_q = (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat()
    t1 = safe_http_json(f'{OPENF1}/car_data?session_key={sk}&driver_number={d1}&date>={now_q}', timeout=4.0) or []
    t2 = safe_http_json(f'{OPENF1}/car_data?session_key={sk}&driver_number={d2}&date>={now_q}', timeout=4.0) or []
    return {
        'ok': True,
        'd1': t1[:100], 
        'd2': t2[:100],
        'sessionName': latest.get('meeting_name')
    }

def esc(s: Any) -> str:
    return html.escape(str(s or ''), quote=True)

def build_live_race_prediction_backend(payload: dict[str, Any]) -> dict[str, Any]:
    sess = payload.get('session') or {}
    if not sess.get('session_key'):
        return {'ok': False, 'error': 'Missing session'}
    sk = sess.get('session_key')
    current_code = payload.get('currentCode') or payload.get('nextCode') or ''
    track_db = payload.get('trackDb') or {}
    tyre_pace = payload.get('tyrePace') or TYRE_PACE_DEFAULT
    tyre_colors = payload.get('tyreColors') or TYRE_COLORS_DEFAULT
    circuit_overtake = payload.get('circuitOvertake') or CIRCUIT_OVERTAKE_DEFAULT
    circuit_modifiers = payload.get('circuitModifiers') or {}
    reliability = payload.get('reliability') or {}
    team_pace = payload.get('teamPace') or {}
    driver_skill = payload.get('driverSkill') or {}
    race_schedule = payload.get('raceSchedule') or []
    live_drivers = payload.get('liveDrivers') or payload.get('fallbackDrivers') or []
    drivers = live_drivers or []
    positions = safe_http_json(f'{OPENF1}/position?session_key={sk}', timeout=6.0) or []
    stints = safe_http_json(f'{OPENF1}/stints?session_key={sk}', timeout=6.0) or []
    race_control = safe_http_json(f'{OPENF1}/race_control?session_key={sk}', timeout=6.0) or []
    laps_data = safe_http_json(f'{OPENF1}/laps?session_key={sk}', timeout=6.0) or []
    live_driver_rows = safe_http_json(f'{OPENF1}/drivers?session_key={sk}', timeout=6.0) or []

    live_drv_map: dict[Any, dict[str, Any]] = {}
    for d in live_driver_rows or []:
        live_drv_map[d.get('driver_number')] = {
            'name': d.get('full_name') or d.get('name_acronym') or f"#{d.get('driver_number')}",
            'team': d.get('team_name') or '',
            'acronym': d.get('name_acronym') or str(d.get('driver_number') or ''),
        }

    lat_pos: dict[Any, dict[str, Any]] = {}
    for p in positions or []:
        dn = p.get('driver_number')
        if dn is None:
            continue
        prev = lat_pos.get(dn)
        if prev is None or str(p.get('date') or '') > str(prev.get('date') or ''):
            lat_pos[dn] = p
    sorted_pos = sorted(lat_pos.values(), key=lambda x: x.get('position', 999))
    if not sorted_pos:
        return {'ok': False, 'error': 'No position data'}

    tyre_map: dict[Any, dict[str, Any]] = {}
    for s in stints or []:
        dn = s.get('driver_number')
        prev = tyre_map.get(dn)
        if prev is None or (s.get('stint_number') or 0) > (prev.get('stint_number') or 0):
            tyre_map[dn] = s

    rc_latest = list(race_control or [])[-10:]
    sc_active = any('SAFETY CAR DEPLOYED' in str(m.get('message') or '').upper() or 'VIRTUAL SAFETY CAR' in str(m.get('message') or '').upper() for m in rc_latest)
    vsc_active = any('VIRTUAL' in str(m.get('message') or '').upper() for m in rc_latest)

    latest_lap_by_driver: dict[Any, dict[str, Any]] = {}
    for l in laps_data or []:
        dn = l.get('driver_number')
        if dn is None:
            continue
        prev = latest_lap_by_driver.get(dn)
        if prev is None or (l.get('lap_number') or 0) > (prev.get('lap_number') or 0):
            latest_lap_by_driver[dn] = l
    laps_completed = max([int((l.get('lap_number') or 0)) for l in latest_lap_by_driver.values()] or [1])
    total_laps = int(((track_db.get(current_code) or {}).get('laps') or 57))
    laps_remaining = max(total_laps - laps_completed, 1)
    race_pct = min(laps_completed / max(total_laps, 1), 0.99)

    team_order = TEAM_ORDER_DEFAULT
    drvs = normalize_driver_standings(drivers, team_order)
    pace_model_arr = build_pace_model(drvs, race_schedule, team_pace, driver_skill)
    overtake_diff = float(circuit_overtake.get(current_code, 0.60))
    circuit_mods = circuit_modifiers.get(current_code) or {}

    race_drivers = []
    for pos_idx, p in enumerate(sorted_pos):
        drv_num = p.get('driver_number')
        api_info = live_drv_map.get(drv_num) or {}
        known = None
        if api_info.get('name'):
            last = str(api_info.get('name')).lower().split(' ')[-1]
            for d in drvs:
                if str(d.get('name') or '').lower().endswith(last):
                    known = d
                    break
        if known is None:
            known = drvs[pos_idx] if pos_idx < len(drvs) else (drvs[0] if drvs else {})
        tyre = tyre_map.get(drv_num) or {}
        tyre_compound = str(tyre.get('compound') or '?')
        tyre_mult = float(tyre_pace.get(tyre_compound, 1.0))
        team = known.get('team') or ''
        team_mod = float((circuit_mods.get(team) or 1.0))
        drv_idx = drvs.index(known) if known in drvs else -1
        skill_team = pace_model_arr[drv_idx] if drv_idx >= 0 else (1 / max(len(drvs), 1))
        pos_penalty = 1.0 - (pos_idx * 0.015 * (1 - overtake_diff))
        
        lap_start = int(tyre.get('lap_start') or laps_completed)
        tyre_age_start = int(tyre.get('tyre_age_at_start') or 0)
        current_age = max(tyre_age_start + max(laps_completed - lap_start, 0), tyre_age_start)
        
        race_drivers.append({
            'position': int(p.get('position') or pos_idx + 1),
            'driverNum': drv_num,
            'name': str(known.get('name') or api_info.get('name') or f'Driver #{drv_num}'),
            'team': team,
            'pace': skill_team * team_mod * tyre_mult * pos_penalty,
            'tyre': tyre_compound,
            'tyrePace': tyre_mult,
            'tyreAge': current_age,
        })

    pace_sum = sum(d['pace'] for d in race_drivers) or 1.0
    norm_paces = [d['pace'] / pace_sum for d in race_drivers]
    runs = max(10_000, min(int(payload.get('runs') or 50_000), 200_000))
    n = len(race_drivers)
    if n == 0:
        return {'ok': False, 'error': 'No drivers in race'}

    weather_res = build_weather_backend(current_code)
    weather = weather_res.get('weather') or {}
    is_wet = float(weather.get('rainChance') or 0.0) > 0.5

    # ── Vectorised live-race prediction with Box-Muller Gaussian noise ────────
    rng = np.random.default_rng()
    pos_weight = max(1.0 - race_pct * 0.6, 0.4)
    pos_bonus = np.array([
        (n - race_drivers[i]['position']) / max(n, 1) * pos_weight * 0.08
        for i in range(n)
    ])  # (n,)
    
    tyre_penalties = np.array([
        race_drivers[i]['tyreAge'] * get_deg_rate(race_drivers[i]['tyre']) * (1.2 if is_wet else 1.0) * 0.005
        for i in range(n)
    ])
    
    base_np  = np.array(norm_paces, dtype=np.float64) - tyre_penalties  # (n,)

    sigma_val = (0.12 if sc_active else 0.07) / 3.0
    # Box-Muller noise (runs × n)
    noise = _box_muller_normal((runs, n), rng) * sigma_val
    sim_pace = base_np[np.newaxis, :] + pos_bonus[np.newaxis, :] + noise  # (runs, n)

    if sc_active or vsc_active:
        field_avg = sim_pace.mean(axis=1, keepdims=True)
        sim_pace = sim_pace * 0.4 + field_avg * 0.6

    order = np.argsort(-sim_pace, axis=1, kind='stable')  # (runs, n) sorted by pace desc
    winners = order[:, 0]                                  # (runs,)
    podium_drivers = order[:, :3].ravel()                  # (runs*3,)
    win_counts  = np.bincount(winners, minlength=n).tolist()
    pod_arr     = np.zeros(n, dtype=np.int64)
    for pos_i in range(3):
        pod_arr += np.bincount(order[:, pos_i], minlength=n)
    pod_counts = pod_arr.tolist()

    win_probs = [round((w / runs) * 1000) / 10 for w in win_counts]
    pod_probs = [round((p / runs) * 1000) / 10 for p in pod_counts]
    ranked = sorted([{**d, 'winProb': win_probs[i], 'podProb': pod_probs[i]} for i, d in enumerate(race_drivers)], key=lambda x: x['winProb'], reverse=True)
    max_prob = max([r['winProb'] for r in ranked] or [1])
    top3 = ranked[:3]
    medals = ['🥇', '🥈', '🥉']
    status_badge = '<span style="background:var(--gold);color:#000;font-size:9px;font-weight:700;padding:3px 8px;border-radius:3px;letter-spacing:1px;">🚗 %s ACTIVE</span>' % ('VSC' if vsc_active else 'SAFETY CAR') if sc_active else '<span style="background:var(--green);color:#000;font-size:9px;font-weight:700;padding:3px 8px;border-radius:3px;letter-spacing:1px;">🟢 RACING</span>'
    track = track_db.get(current_code) or {}
    top3_html = ''.join([
        f'''
          <div class="pod-step p{i + 1}" style="border-top-color:{esc(get_tc(d.get("team")))}">
            <div class="pod-num">{d.get("position")}</div>
            <div style="width:32px;height:32px;margin-right:12px;opacity:0.9;">{get_team_logo(d.get("team"), size=32)}</div>
            <div class="pod-drv">{esc(str(d.get("name") or "").split(" ")[-1])}</div>
            <div class="pod-tm">{esc(d.get("team"))}</div>
            <div class="pod-ppts">{d.get("winProb")}% WIN</div>
            <div style="background:{esc(tyre_colors.get(d.get("tyre"), "#5a6278"))};color:#000;font-size:8px;font-weight:700;padding:1px 5px;border-radius:2px;margin-top:4px;display:inline-block;">{esc(d.get("tyre"))}</div>
          </div>''' for i, d in enumerate(top3)
    ])
    all_rows = []
    for i, d in enumerate(ranked):
        col = get_tc(d.get('team'))
        bw = max((float(d.get('winProb') or 0) / max_prob) * 100, 0.5)
        rc = 'var(--gold)' if i == 0 else 'var(--silver)' if i == 1 else '#cd7f32' if i == 2 else 'var(--muted)'
        prob = '<span style="color:var(--muted);font-size:9px;">&lt;0.1%</span>' if float(d.get('winProb') or 0) == 0 else f"{d.get('winProb')}%"
        tyre_initial = esc((str(d.get('tyre') or '?')[:1]))
        all_rows.append(f'''<div style="display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid var(--border);">
            <div style="width:18px;text-align:right;font-family:Orbitron,sans-serif;font-size:9px;color:{rc};flex-shrink:0;">{d.get('position')}</div>
            <div style="width:130px;font-size:10px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{esc(d.get('name'))}</div>
            <div style="background:{esc(tyre_colors.get(d.get('tyre'), '#5a6278'))};color:#000;font-size:8px;font-weight:700;padding:1px 4px;border-radius:2px;flex-shrink:0;">{tyre_initial}</div>
            <div style="flex:1;height:4px;background:var(--border);border-radius:2px;overflow:hidden;">
              <div class="lr-bar" data-w="{bw}" style="height:100%;width:0%;background:{col};border-radius:2px;transition:width .8s ease;"></div>
            </div>
            <div style="width:36px;text-align:right;font-family:Orbitron,sans-serif;font-size:10px;color:{col};flex-shrink:0;">{prob}</div>
            <div style="width:44px;text-align:right;font-size:9px;color:var(--muted);flex-shrink:0;">{d.get('podProb')}% pod</div>
          </div>''')
    title = f"🔴 LIVE: {str((track.get('name') or sess.get('meeting_name') or 'Race')).upper()}"
    content_html = f'''
      <div style="display:flex;align-items:center;gap:10px;padding:8px 0 12px;border-bottom:1px solid var(--border);margin-bottom:12px;flex-wrap:wrap;">
        <span style="font-size:22px;">{esc(track.get('flag') or '🏁')}</span>
        <div>
          <div style="font-family:Barlow Condensed,sans-serif;font-size:14px;font-weight:700;">LAP {laps_completed} / {total_laps} &nbsp;·&nbsp; {laps_remaining} REMAINING</div>
          <div style="font-size:10px;color:var(--muted);margin-top:2px;">{esc(track.get('name') or sess.get('meeting_name') or '')}</div>
        </div>
        <div style="margin-left:auto;display:flex;align-items:center;gap:8px;">
          {status_badge}
          <span style="font-size:9px;color:var(--muted);">Updates every 30s</span>
        </div>
      </div>
      <div style="font-family:Barlow Condensed,sans-serif;font-size:11px;font-weight:700;letter-spacing:3px;color:var(--muted);margin-bottom:10px;">LIVE WIN PREDICTION</div>
      <div class="podium-row" style="margin-bottom:14px;">
        {top3_html}
      </div>
      <div style="font-family:Barlow Condensed,sans-serif;font-size:11px;font-weight:700;letter-spacing:3px;color:var(--muted);margin-bottom:6px;">ALL DRIVERS</div>
      <div style="max-height:360px;overflow-y:auto;">
        {''.join(all_rows)}
      </div>
      <div style="font-size:9px;color:var(--muted);margin-top:8px;">20,000 simulated remaining laps · Position + tyre + pace model · {'SC compression applied' if sc_active else 'Normal racing conditions'}</div>'''
    return {'ok': True, 'titleText': title, 'contentHtml': content_html}

@legacy_api.post('/api/team-analysis')
def api_team_analysis() -> Any:
    payload = request.get_json(silent=True) or {}
    return jsonify(build_team_analysis(payload))

@legacy_api.get('/api/load-standings')
def api_load_standings() -> Any:
    live_drivers: list[dict[str, Any]] = []
    live_constructors: list[dict[str, Any]] = []
    got_any = False
    status_openf1 = 'loading'
    status_ergast = 'loading'
    badge_text = 'CACHED'
    badge_live = False
    source_provider = 'fallback'
    
    # Track if we successfully reached the servers at all
    reached_openf1 = False
    reached_ergast = False

    try:
        # 1. Fetch sessions
        sessions_data = safe_http_json(f'{OPENF1}/sessions?year={CURRENT_F1_YEAR}&session_type=Race', timeout=8.0)
        if sessions_data is not None:
            reached_openf1 = True
            sessions = sessions_data or []
        else:
            sessions = []

        # Sort sessions by date descending to try latest first
        sessions_sorted = sorted(sessions, key=lambda s: s.get('date_start', ''), reverse=True)
        
        # Try up to 3 most recent sessions that have actually started
        now = datetime.now(timezone.utc)
        valid_sk_found = False
        for latest in sessions_sorted:
            start_dt = parse_iso_datetime(latest.get('date_start'))
            if not start_dt or start_dt > now:
                continue

            sk = latest.get('session_key')
            if not sk:
                continue

            d_data = safe_http_json(f'{OPENF1}/championship_drivers?session_key={sk}', timeout=6.0, use_cache=True)
            if d_data is not None:
                API_CACHE.set(f'{OPENF1}/championship_drivers?session_key={sk}', d_data, ttl=3600.0)
            
            c_data = safe_http_json(f'{OPENF1}/championship_teams?session_key={sk}', timeout=6.0, use_cache=True)
            if c_data is not None:
                API_CACHE.set(f'{OPENF1}/championship_teams?session_key={sk}', c_data, ttl=3600.0)
            
            if d_data is None and c_data is None:
                # This check means safe_http_json caught an exception (timeout/error)
                continue
            
            # Even if they are empty lists, we successfully reached the endpoint for standings
            valid_sk_found = True
            d_data = d_data or []
            c_data = c_data or []
            
            if not d_data and not c_data:
                # If this session has no data yet, try the previous one
                logger.info(f"OpenF1: No championship data for session {sk} ({latest.get('session_name')}), trying previous...")
                continue

            drivers_meta = safe_http_json(f'{OPENF1}/drivers?session_key={sk}', timeout=6.0, use_cache=True) or []
            if drivers_meta:
                API_CACHE.set(f'{OPENF1}/drivers?session_key={sk}', drivers_meta, ttl=3600.0)
            driver_meta_by_no = {
                int(d.get('driver_number')): d for d in drivers_meta
                if str(d.get('driver_number') or '').strip().isdigit()
            }
            if isinstance(d_data, list) and d_data:
                rows = sorted(d_data, key=lambda d: (int(float(d.get('position_current') or 999)), -(float(d.get('points_current') or 0))))
                parsed_drivers = []
                for i, d in enumerate(rows):
                    driver_no = d.get('driver_number')
                    meta = driver_meta_by_no.get(int(driver_no)) if str(driver_no or '').strip().isdigit() else {}
                    parsed_drivers.append({
                        'pos': int(float(d.get('position_current') or (i + 1))),
                        'name': normalize_driver_name(meta.get('full_name') or meta.get('broadcast_name') or f'Driver {driver_no or i + 1}'),
                        'team': meta.get('team_name') or '',
                        'pts': int(float(d.get('points_current') or 0)),
                    })
                live_drivers = normalize_driver_standings(parsed_drivers, TEAM_ORDER_DEFAULT)
            if isinstance(c_data, list) and c_data:
                rows = sorted(c_data, key=lambda d: (int(float(d.get('position_current') or 999)), -(float(d.get('points_current') or 0))))
                live_constructors = normalize_constructors_standings([
                    {
                        'pos': int(float(d.get('position_current') or (i + 1))),
                        'name': d.get('team_name') or 'Unknown',
                        'pts': int(float(d.get('points_current') or 0)),
                    }
                    for i, d in enumerate(rows)
                ], TEAM_ORDER_DEFAULT)
            
            if live_drivers or live_constructors:
                got_any = True
                source_provider = 'openf1'
                end = parse_iso_datetime(latest.get('date_end'))
                is_live = bool(start_dt and start_dt <= now and (end is None or end > now))
                badge_text = 'LIVE' if is_live else 'LIVE DATA'
                badge_live = is_live
                break # We found valid data
        
        status_openf1 = 'ok' if (reached_openf1 or valid_sk_found) else 'err'
    except Exception as e:
        logger.error(f"OpenF1 standings fetch failed: {e}")
        status_openf1 = 'err'
    try:
        d_json = safe_http_json(f'{JOLPICA}/{CURRENT_F1_YEAR}/driverStandings.json', timeout=7.0)
        c_json = safe_http_json(f'{JOLPICA}/{CURRENT_F1_YEAR}/constructorStandings.json', timeout=7.0)
        
        if d_json is not None or c_json is not None:
            reached_ergast = True
            
        d_lists = (((d_json or {}).get('MRData') or {}).get('StandingsTable') or {}).get('StandingsLists') or []
        c_lists = (((c_json or {}).get('MRData') or {}).get('StandingsTable') or {}).get('StandingsLists') or []
        d_list = (d_lists[0] or {}).get('DriverStandings') if d_lists else []
        c_list = (c_lists[0] or {}).get('ConstructorStandings') if c_lists else []
        if d_list and not live_drivers:
            live_drivers = normalize_driver_standings([
                {'pos': int(d.get('position') or i + 1), 'pts': int(float(d.get('points') or 0)), 'name': f"{((d.get('Driver') or {}).get('givenName') or '').strip()} {((d.get('Driver') or {}).get('familyName') or '').strip()}".strip(), 'team': ((d.get('Constructors') or [{}])[0].get('name') or '')}
                for i, d in enumerate(d_list)
            ], TEAM_ORDER_DEFAULT)
            got_any = True
            badge_text = 'LIVE DATA'
            source_provider = 'jolpica'
        if c_list and not live_constructors:
            live_constructors = normalize_constructors_standings([
                {'pos': int(c.get('position') or i + 1), 'pts': int(float(c.get('points') or 0)), 'name': (c.get('Constructor') or {}).get('name') or ''}
                for i, c in enumerate(c_list)
            ], TEAM_ORDER_DEFAULT)
            got_any = True
            if source_provider == 'fallback':
                source_provider = 'jolpica'
        status_ergast = 'ok' if reached_ergast else 'err'
    except Exception as e:
        logger.error(f"Ergast/Jolpica fetch failed: {e}")
        status_ergast = 'err'
    if not got_any:
        badge_text = 'CACHED'
        source_provider = 'fallback'
        badge_live = False
    return jsonify({
        'ok': True,
        'liveDrivers': live_drivers,
        'liveConstructors': live_constructors,
        'statusOpenF1': status_openf1,
        'statusErgast': status_ergast,
        'badgeText': badge_text,
        'badgeLive': badge_live,
        'sourceProvider': source_provider,
    })

@legacy_api.post('/api/live-race-prediction')
def api_live_race_prediction() -> Any:
    payload = request.get_json(silent=True) or {}
    return jsonify(build_live_race_prediction_backend(payload))

@legacy_api.get('/api/live-session')
def api_live_session() -> Any:
    sess, is_live = latest_race_session_backend()
    if not sess:
        return jsonify({'ok': False, 'isLive': False, 'session': None, 'error': 'No race session found'})
    return jsonify({'ok': True, 'isLive': is_live, 'session': sess})

@legacy_api.get('/api/current-race-session')
def api_current_race_session() -> Any:
    return api_live_session()

def build_projected_strategy_fallback(track_code: str = 'MIA') -> dict[str, Any]:
    total_laps = infer_total_laps(track_code)
    fallback_drivers = []
    try:
        fallback_drivers = BOOTSTRAP_DATA.get('FALLBACK_DRIVERS') or BOOTSTRAP_DATA.get('DRIVERS') or []
    except Exception:
        fallback_drivers = []
    if not fallback_drivers:
        fallback_drivers = [
            {'name': 'Lando Norris', 'team': 'McLaren'},
            {'name': 'Max Verstappen', 'team': 'Red Bull'},
            {'name': 'Charles Leclerc', 'team': 'Ferrari'},
            {'name': 'George Russell', 'team': 'Mercedes'},
            {'name': 'Lewis Hamilton', 'team': 'Ferrari'},
        ]
    events = [
        timeline_event(
            1, min(8, total_laps), 'Opening tyre management', 'stint', 'low',
            'Projected start phase. Drivers protect tyres and avoid early damage.'
        ),
        timeline_event(
            12, 20, 'Soft tyre pit window', 'pit-window', 'medium',
            'Projected first pit window for aggressive soft-start strategies.'
        ),
        timeline_event(
            18, 30, 'Medium tyre pit window', 'pit-window', 'medium',
            'Projected medium-to-hard crossover window for standard one-stop plans.'
        ),
        timeline_event(
            max(35, total_laps - 18), total_laps, 'Final stint management', 'final-stint', 'low',
            'Projected final stint. Avoid extra stop unless tyre degradation, rain, or Safety Car changes the race.'
        )
    ]
    recommendations = []
    for idx, d in enumerate(fallback_drivers[:22]):
        compound = 'MEDIUM'
        age = 0
        track_wear = 'Medium'
        rain_pct = 0
        next_compound = choose_next_compound(compound, rain_pct, age, track_wear)
        pit_window = estimate_pit_window(compound, age, track_wear)
        undercut = {
            'viable': False,
            'reason': 'Projected mode. Live gap data is not available.',
            'targetGap': DEFAULT_PIT_LOSS_BY_TRACK.get(track_code, PIT_LANE_LOSS),
            'gapAhead': None,
        }
        recommendations.append({
            'driverNumber': idx + 1,
            'name': d.get('name') or f'Driver {idx + 1}',
            'team': d.get('team') or 'Unknown',
            'compound': compound,
            'tyreAge': age,
            'lifeRemaining': tyre_life_remaining(compound, age, track_wear),
            'degradationPenalty': tyre_degradation_penalty(compound, age, track_wear),
            'recommendedCompound': next_compound,
            'pitWindow': pit_window,
            'undercut': undercut,
            'undercutStatus': 'NO_GAP_DATA',
            'gapAhead': None,
            'alerts': ['Projected fallback. Waiting for live stint and gap data.'],
            'action': 'EXTEND',
            'priorityScore': 10,
            'summary': f"{d.get('name') or 'Driver'} is in projected extend mode. Live stint and gap data are not available yet."
        })
    return {
        'ok': True, 'isLive': False, 'isProjected': True, 'sessionKey': None, 'trackCode': track_code,
        'currentLap': 1, 'totalLaps': total_laps, 'trackWear': 'Projected', 'rainPct': 0,
        'mode': 'PROJECTED STRATEGY', 'safetyCarWindow': False, 'generatedAt': time.time(),
        'events': events, 'recommendations': recommendations,
    }

def build_race_strategy_timeline(track_code: str | None = None, simulate_rain: bool = False) -> dict[str, Any]:
    sess, is_live = latest_race_session_backend()

    if not sess or not sess.get('session_key'):
        return {
            'ok': False,
            'error': 'No live or recent race session found',
            'events': []
        }

    sk = sess.get('session_key')
    track_code = str(track_code or get_track_code_from_session(sess) or 'MIA').upper()
    total_laps = infer_total_laps(track_code)

    now = datetime.now(timezone.utc)
    lookback = now - timedelta(minutes=10)
    anchor_q = urllib.parse.quote(iso_utc(lookback), safe='')

    laps = safe_http_json(
        f'{OPENF1}/laps?session_key={sk}&date>={anchor_q}',
        timeout=5.0,
        ttl=OPENF1_HEAVY_FETCH_TTL
    ) or []

    race_control = safe_http_json(
        f'{OPENF1}/race_control?session_key={sk}&date>={anchor_q}',
        timeout=5.0,
        ttl=OPENF1_HEAVY_FETCH_TTL
    ) or []

    current_lap = current_lap_from_laps(laps)
    if current_lap <= 0:
        current_lap = 1

    # Reuse the existing tyre strategy logic via internal call or mock request context
    with app.test_request_context(
        f"/api/tyre-strategy?trackCode={urllib.parse.quote(track_code)}&simulateRain={'1' if simulate_rain else '0'}"
    ):
        tyre_resp = api_tyre_strategy()
        tyre_data = tyre_resp.get_json() if hasattr(tyre_resp, 'get_json') else {}

    if not tyre_data or not tyre_data.get('ok'):
        return {
            'ok': False,
            'error': tyre_data.get('error') if isinstance(tyre_data, dict) else 'Tyre strategy unavailable',
            'events': []
        }

    recs = tyre_data.get('recommendations') or []
    rain_pct = int(tyre_data.get('rainPct') or 0)
    mode = tyre_data.get('mode') or 'UNKNOWN'
    track_wear = tyre_data.get('trackWear') or 'Medium'
    sc_active = bool(tyre_data.get('safetyCarWindow') or race_control_has_sc_or_vsc(race_control))

    events: list[dict[str, Any]] = []

    # Race opening phase
    if current_lap <= 8:
        events.append(timeline_event(
            1,
            min(8, total_laps),
            'Opening tyre management',
            'stint',
            'low',
            'Drivers are expected to build tyre temperature, avoid early damage, and protect track position.'
        ))

    # Driver specific pit windows
    for r in recs:
        name = r.get('name') or f"#{r.get('driverNumber')}"
        team = r.get('team') or ''
        compound = r.get('compound') or 'MEDIUM'
        next_compound = r.get('recommendedCompound') or choose_next_compound(compound, rain_pct, int(r.get('tyreAge') or 0), track_wear)
        pit = r.get('pitWindow') or {}
        undercut = r.get('undercut') or {}

        recommended_in = int(pit.get('recommendedInLaps') or 0)
        urgency = pit.get('urgency') or 'UNKNOWN'
        life_left = int(r.get('lifeRemaining') or 0)

        pit_lap = max(current_lap, min(total_laps, current_lap + recommended_in))
        window_start = max(current_lap, pit_lap - 2)
        window_end = min(total_laps, pit_lap + max(2, min(life_left, 6)))

        severity = timeline_event_severity_for_urgency(urgency)

        if urgency in {'BOX NOW', 'PIT WINDOW OPEN', 'PREPARE PIT WINDOW'}:
            events.append(timeline_event(
                window_start,
                window_end,
                f'{name}: {urgency}',
                'pit-window',
                severity,
                f'{name} should consider switching from {compound} to {next_compound}. Tyre life left: {life_left} laps.',
                drivers=[name],
                teams=[team] if team else [],
                compound_from=compound,
                compound_to=next_compound,
            ))

        if undercut.get('viable'):
            events.append(timeline_event(
                current_lap,
                min(total_laps, current_lap + 3),
                f'{name}: undercut opportunity',
                'undercut',
                'high',
                f'Undercut appears viable. Gap ahead: {undercut.get("gapAhead")}s. Target gap: {undercut.get("targetGap")}s.',
                drivers=[name],
                teams=[team] if team else [],
                compound_from=compound,
                compound_to=next_compound,
            ))

        if urgency == 'EXTEND STINT' and life_left >= 8:
            events.append(timeline_event(
                current_lap,
                min(total_laps, current_lap + min(life_left, 10)),
                f'{name}: extend stint',
                'extend',
                'low',
                f'{name} can extend the current {compound} stint. Current tyre life estimate remains stable.',
                drivers=[name],
                teams=[team] if team else [],
                compound_from=compound,
                compound_to=next_compound,
            ))

    # Rain crossover events
    if rain_pct >= 70:
        events.append(timeline_event(
            current_lap,
            min(total_laps, current_lap + 5),
            'Wet crossover warning',
            'weather',
            'critical',
            'Rain risk is high. Dry tyre runners should prepare for Wet or Intermediate crossover depending on standing water.'
        ))
    elif rain_pct >= 40:
        events.append(timeline_event(
            current_lap,
            min(total_laps, current_lap + 8),
            'Intermediate crossover watch',
            'weather',
            'high',
            'Mixed conditions are possible. Teams should prepare Intermediates and watch lap time crossover.'
        ))

    # Safety Car / VSC event
    if sc_active:
        events.append(timeline_event(
            current_lap,
            min(total_laps, current_lap + 2),
            'Safety Car or VSC pit opportunity',
            'safety-car',
            'critical',
            'Safety Car or VSC may reduce pit loss. Drivers near a pit window should strongly consider stopping.'
        ))

    # Final stint phase
    if total_laps - current_lap <= 15:
        events.append(timeline_event(
            current_lap,
            total_laps,
            'Final stint decision zone',
            'final-stint',
            'medium',
            'Teams should avoid unnecessary stops unless tyre life is critical, rain arrives, or a Safety Car opens a cheap stop.'
        ))

    # Sort by lap and severity
    severity_rank = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    events.sort(key=lambda e: (e.get('lapStart', 999), severity_rank.get(e.get('severity'), 9)))

    return {
        'ok': True,
        'isLive': is_live,
        'sessionKey': sk,
        'trackCode': track_code,
        'currentLap': current_lap,
        'totalLaps': total_laps,
        'trackWear': track_wear,
        'rainPct': rain_pct,
        'mode': mode,
        'safetyCarWindow': sc_active,
        'generatedAt': time.time(),
        'events': events[:40],
    }

@legacy_api.get('/api/race-strategy-timeline')
def api_race_strategy_timeline() -> Any:
    track_code = str(request.args.get('trackCode') or 'MIA').upper()
    simulate_rain = str(request.args.get('simulateRain') or '').lower() in {'1', 'true', 'yes', 'on'}

    try:
        data = build_race_strategy_timeline(track_code=track_code, simulate_rain=simulate_rain)
        if not isinstance(data, dict) or not data.get('ok'):
            data = build_projected_strategy_fallback(track_code)
        return jsonify(data)
    except Exception as e:
        logger.exception('Race strategy timeline failed')
        return jsonify(build_projected_strategy_fallback(track_code)), 200

@legacy_api.get('/api/driver-headshots')
def api_driver_headshots() -> Any:
    sess, _ = latest_race_session_backend()

    photos: dict[str, str] = dict(DRIVER_HEADSHOT_OVERRIDES)

    if sess and sess.get('session_key'):
        try:
            _, _, live_photos = live_driver_team_map_for_session(sess.get('session_key'))
            if live_photos:
                # OpenF1 photos are useful, but local overrides should remain priority.
                photos = {**live_photos, **DRIVER_HEADSHOT_OVERRIDES}
        except Exception as e:
            logger.warning(f'Driver headshot fetch failed, using overrides: {e}')

    resp = jsonify({
        'ok': True,
        'photos': photos,
        'sessionKey': sess.get('session_key') if sess else None,
        'source': 'overrides+openf1',
        'generatedAt': time.time()
    })
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp

@legacy_api.post('/api/transcribe-radio')
def api_transcribe_radio() -> Any:
    payload = request.get_json(silent=True) or {}
    audio_url = str(payload.get('url') or '').strip()
    force = bool(payload.get('force'))
    result = transcribe_audio_url(audio_url, force=force)
    return jsonify(result)

@legacy_api.post('/api/backtest')
def api_backtest() -> Any:
    payload = request.get_json(silent=True) or {}
    races = payload.get('races') or []
    if not races:
        return jsonify({'ok': False, 'error': 'No races supplied for backtest'})
    results = []
    for race in races:
        predicted = race.get('predictedWinner')
        actual = race.get('actualWinner')
        correct = bool(predicted and actual and predicted == actual)
        results.append({'raceName': race.get('raceName') or 'Unknown', 'predictedWinner': predicted,
                        'actualWinner': actual, 'winnerCorrect': correct})
    total = len(results)
    correct_count = sum(1 for r in results if r['winnerCorrect'])
    return jsonify({'ok': True, 'totalRaces': total,
                    'winnerAccuracy': correct_count / total if total else 0.0, 'results': results})

@legacy_api.get('/api/h2h-telemetry')
def api_h2h_telemetry() -> Any:
    d1 = request.args.get('d1', '44')
    d2 = request.args.get('d2', '1')
    return jsonify(build_telemetry_h2h_backend(d1, d2))

def default_dynamic_bios() -> dict[str, Any]:
    return {
        "lastProcessedSessionKey": None,
        "lastUpdated": None,
        "drivers": {},
        "teams": {}
    }

def load_dynamic_bios() -> dict[str, Any]:
    if not DYNAMIC_BIOS_PATH.exists():
        data = default_dynamic_bios()
        save_dynamic_bios(data)
        return data

    try:
        data = json.loads(DYNAMIC_BIOS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default_dynamic_bios()

        data.setdefault("lastProcessedSessionKey", None)
        data.setdefault("lastUpdated", None)
        data.setdefault("drivers", {})
        data.setdefault("teams", {})
        return data

    except Exception as e:
        logger.warning(f"Could not read dynamic bios file: {e}")
        return default_dynamic_bios()

def save_dynamic_bios(data: dict[str, Any]) -> None:
    try:
        DYNAMIC_BIOS_PATH.parent.mkdir(parents=True, exist_ok=True)
        DYNAMIC_BIOS_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"Could not save dynamic bios file: {e}")

def latest_completed_weekend_session() -> dict[str, Any] | None:
    sessions = safe_http_json(
        f"{OPENF1}/sessions?year={CURRENT_F1_YEAR}",
        timeout=8.0,
        ttl=300.0
    ) or []

    now = datetime.now(timezone.utc)
    completed: list[dict[str, Any]] = []

    for s in sessions:
        end = parse_iso_datetime(s.get("date_end"))
        if not end:
            continue
        # Wait 10 minutes after session end so OpenF1 data has time to settle.
        if end + timedelta(minutes=10) <= now:
            completed.append(s)

    if not completed:
        return None

    completed.sort(
        key=lambda x: parse_iso_datetime(x.get("date_end")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True
    )
    return completed[0]

def session_type_label(session: dict[str, Any]) -> str:
    raw = str(session.get("session_name") or session.get("session_type") or "Session").strip()
    lower = raw.lower()

    if "practice" in lower or lower in {"fp1", "fp2", "fp3"}:
        return raw.upper() if raw.lower().startswith("fp") else raw
    if "sprint" in lower and "qualifying" in lower:
        return "Sprint Qualifying"
    if "qualifying" in lower:
        return "Qualifying"
    if "sprint" in lower:
        return "Sprint"
    if "race" in lower:
        return "Race"
    return raw or "Session"

def meeting_label(session: dict[str, Any]) -> str:
    return (
        session.get("meeting_name")
        or session.get("meeting_official_name")
        or session.get("location")
        or "Race Weekend"
    )

def best_lap_by_driver(laps: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    best: dict[Any, dict[str, Any]] = {}
    for lap in laps or []:
        dn = lap.get("driver_number")
        duration = lap.get("lap_duration")
        if dn is None or duration is None:
            continue
        try:
            dur = float(duration)
        except Exception:
            continue
        prev = best.get(dn)
        if prev is None:
            best[dn] = lap
            continue
        try:
            prev_dur = float(prev.get("lap_duration") or 999999)
        except Exception:
            prev_dur = 999999
        if dur < prev_dur:
            best[dn] = lap
    return best

def latest_position_by_driver(positions: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    return latest_by_key(positions, "driver_number")

def position_text(pos: Any) -> str:
    if pos is None:
        return "unclassified"
    try:
        return f"P{int(float(pos))}"
    except Exception:
        return str(pos)

def format_lap_time(value: Any) -> str | None:
    if value is None:
        return None
    try:
        seconds = float(value)
    except Exception:
        return None
    minutes = int(seconds // 60)
    rem = seconds - minutes * 60
    if minutes > 0:
        return f"{minutes}:{rem:06.3f}"
    return f"{seconds:.3f}s"

def build_session_bio_updates(session: dict[str, Any]) -> dict[str, Any]:
    sk = session.get("session_key")
    if not sk:
        return {"drivers": {}, "teams": {}}

    sess_name = session_type_label(session)
    meeting = meeting_label(session)

    drivers = safe_http_json(f"{OPENF1}/drivers?session_key={sk}", timeout=6.0, ttl=300.0) or []
    positions = safe_http_json(f"{OPENF1}/position?session_key={sk}", timeout=6.0, ttl=300.0) or []
    laps = safe_http_json(f"{OPENF1}/laps?session_key={sk}", timeout=6.0, ttl=300.0) or []

    driver_map: dict[Any, dict[str, Any]] = {}
    for d in drivers:
        dn = d.get("driver_number")
        if dn is None:
            continue
        full_name = normalize_driver_name(d.get("full_name") or d.get("name_acronym") or f"Driver {dn}")
        team_name = canonical_team_name(d.get("team_name") or "", TEAM_ORDER_DEFAULT)
        driver_map[dn] = {
            "driverNumber": dn,
            "name": full_name,
            "team": team_name,
            "acronym": d.get("name_acronym") or str(dn),
        }

    latest_pos = latest_position_by_driver(positions)
    best_lap = best_lap_by_driver(laps)

    driver_updates: dict[str, dict[str, Any]] = {}
    team_buckets: dict[str, list[dict[str, Any]]] = {}
    sess_lower = sess_name.lower()

    for dn, info in driver_map.items():
        pos_row = latest_pos.get(dn) or {}
        lap_row = best_lap.get(dn) or {}

        position = pos_row.get("position")
        lap_number = lap_row.get("lap_number")
        lap_duration = lap_row.get("lap_duration")
        lap_time = format_lap_time(lap_duration)

        name = info["name"]
        team = info["team"]
        pos_label = position_text(position)

        # Session-type-specific summary templates
        if "practice" in sess_lower or sess_lower.startswith("fp"):
            summary = f"After {meeting} {sess_name}, {name} completed running with a best available lap of {lap_time or 'no recorded time'}."
        elif sess_lower == "qualifying":
            if position is not None:
                summary = f"After {meeting} Qualifying, {name} was classified {pos_label}."
            else:
                summary = f"After {meeting} Qualifying, {name} appeared in the latest session feed."
        elif sess_lower == "sprint qualifying":
            if position is not None:
                summary = f"After {meeting} Sprint Qualifying, {name} was classified {pos_label}."
            else:
                summary = f"After {meeting} Sprint Qualifying, {name} appeared in the session feed."
        elif sess_lower == "sprint":
            if position is not None:
                summary = f"After {meeting} Sprint, {name} was classified {pos_label} in the sprint session."
            else:
                summary = f"After {meeting} Sprint, {name} appeared in the session feed."
        elif sess_lower == "race":
            if position is not None:
                summary = f"After {meeting} Race, {name} finished {pos_label}."
            else:
                summary = f"After {meeting} Race, {name} appeared in the latest session feed."
        else:
            if position is not None:
                summary = f"After {meeting} {sess_name}, {name} was classified {pos_label}."
            else:
                summary = f"After {meeting} {sess_name}, {name} appeared in the latest available session feed."

        if lap_number and "practice" not in sess_lower:
            summary += f" Best available lap came on lap {lap_number}."
        if lap_time and "practice" not in sess_lower:
            summary += f" Best available lap time: {lap_time}."

        if sess_lower == "race" and position is not None:
            try:
                p = int(float(position))
                if p == 1:
                    summary += " This was a race winning performance."
                elif p <= 3:
                    summary += " This was a podium finish."
                elif p <= 10:
                    summary += " This result scored championship points."
            except Exception:
                pass

        driver_updates[name] = {
            "sessionKey": sk,
            "meeting": meeting,
            "sessionName": sess_name,
            "updatedAt": time.time(),
            "summary": summary,
            "position": position,
            "positionLabel": pos_label,
            "team": team,
            "lapNumber": lap_number,
            "lapDuration": lap_duration,
            "lapTime": lap_time,
        }

        team_buckets.setdefault(team, []).append({
            "name": name,
            "position": position,
            "positionLabel": pos_label,
            "lapDuration": lap_duration,
            "lapTime": lap_time,
        })

    team_updates: dict[str, dict[str, Any]] = {}

    for team, rows in team_buckets.items():
        valid_positions = []
        for r in rows:
            try:
                if r.get("position") is not None:
                    valid_positions.append(int(float(r["position"])))
            except Exception:
                pass

        surnames = ", ".join(str(r["name"]).split()[-1] for r in rows if r.get("name"))

        if valid_positions:
            best_pos = min(valid_positions)
            if sess_lower == "qualifying":
                summary = f"After {meeting} Qualifying, {team}'s best classified car was P{best_pos}."
            elif sess_lower == "race":
                summary = f"After {meeting} Race, {team}'s best finisher was classified P{best_pos}."
            else:
                summary = (
                    f"After {meeting} {sess_name}, {team} had {surnames} recorded in the session feed. "
                    f"The team's best classified position was P{best_pos}."
                )
            if len(valid_positions) >= 2:
                avg_pos = sum(valid_positions) / len(valid_positions)
                summary += f" Average classified position: P{avg_pos:.1f}."
        else:
            summary = (
                f"After {meeting} {sess_name}, {team} had {surnames or 'its drivers'} recorded in the latest session feed."
            )

        team_updates[team] = {
            "sessionKey": sk,
            "meeting": meeting,
            "sessionName": sess_name,
            "updatedAt": time.time(),
            "summary": summary,
            "drivers": rows,
        }

    return {"drivers": driver_updates, "teams": team_updates}

@legacy_api.get('/api/dynamic-bios')
def api_dynamic_bios() -> Any:
    return jsonify({"ok": True, "data": load_dynamic_bios()})

@legacy_api.post('/api/update-bios')
def api_update_bios() -> Any:
    session = latest_completed_weekend_session()

    if not session or not session.get("session_key"):
        return jsonify({"ok": False, "error": "No completed session available yet"})

    current = load_dynamic_bios()
    sk = session.get("session_key")

    if current.get("lastProcessedSessionKey") == sk:
        return jsonify({
            "ok": True,
            "skipped": True,
            "reason": "Session already processed",
            "sessionKey": sk,
            "data": current
        })

    updates = build_session_bio_updates(session)
    current["lastProcessedSessionKey"] = sk
    current["lastUpdated"] = time.time()
    current["drivers"].update(updates.get("drivers") or {})
    current["teams"].update(updates.get("teams") or {})
    save_dynamic_bios(current)

    return jsonify({
        "ok": True,
        "sessionKey": sk,
        "updatedDrivers": len(updates.get("drivers") or {}),
        "updatedTeams": len(updates.get("teams") or {}),
        "data": current
    })