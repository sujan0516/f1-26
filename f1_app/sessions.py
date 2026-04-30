import time
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Tuple, List, Dict
from .config import OPENF1, CURRENT_F1_YEAR, DRIVER_HEADSHOT_OVERRIDES
from .http_client import safe_http_json
from .track_codes import get_track_code_from_session
from .utils import parse_iso_datetime, normalize_driver_name

logger = logging.getLogger('f1_app')

def latest_session_from_list(sessions: List[Dict[str, Any]], now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    if not sessions:
        return None
    now = now or datetime.now(timezone.utc)

    def dt_for(s: Dict[str, Any], *keys: str) -> datetime:
        for key in keys:
            dt = parse_iso_datetime(s.get(key))
            if dt:
                return dt
        return datetime.min.replace(tzinfo=timezone.utc)

    enriched: List[Tuple[Dict[str, Any], datetime, datetime]] = []
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

def latest_race_session_backend() -> Tuple[Optional[Dict[str, Any]], bool]:
    url = f"{OPENF1}/sessions?year={CURRENT_F1_YEAR}&session_type=Race"
    sessions = safe_http_json(url, timeout=5.0) or []
    if not sessions:
        return None, False
    
    latest = latest_session_from_list(sessions)
    if not latest:
        return None, False
        
    now = datetime.now(timezone.utc)
    start = parse_iso_datetime(latest.get("date_start"))
    end = parse_iso_datetime(latest.get("date_end"))
    
    is_live = bool(start and end and start <= now <= end)
    return latest, is_live

def live_driver_team_map_for_session(session_key: Any) -> Tuple[List[Dict[str, Any]], Dict[Any, str], Dict[str, str]]:
    rows = safe_http_json(f'{OPENF1}/drivers?session_key={session_key}', timeout=6.0) or []
    driver_team_map: Dict[Any, str] = {}
    photo_map: Dict[str, str] = {}
    for d in rows or []:
        dn = d.get('driver_number')
        if dn is not None:
            driver_team_map[dn] = d.get('team_name') or ''
        photo_url = d.get('headshot_url')
        full = normalize_driver_name(d.get('full_name'))
        if full and full in DRIVER_HEADSHOT_OVERRIDES:
            photo_url = DRIVER_HEADSHOT_OVERRIDES[full]
        if photo_url:
            if full:
                photo_map[full] = photo_url
                photo_map[str(d.get('full_name') or '')] = photo_url
            broadcast = normalize_driver_name(d.get('broadcast_name'))
            if broadcast:
                photo_map[broadcast] = photo_url
                photo_map[str(d.get('broadcast_name') or '')] = photo_url
            last = normalize_driver_name(d.get('last_name'))
            if last:
                photo_map[last] = photo_url
            if d.get('last_name'):
                photo_map['_' + str(d.get('last_name')).upper()] = photo_url
    return rows, driver_team_map, photo_map

def infer_total_laps(track_code: str) -> int:
    LAPS = {
        'AUS': 58, 'CHN': 56, 'JPN': 53, 'MIA': 57, 'CAN': 70,
        'MON': 78, 'BCN': 66, 'AUT': 71, 'GBR': 52, 'BEL': 44,
        'HUN': 70, 'NED': 72, 'ITA': 53, 'MAD': 66, 'AZE': 51,
        'SGP': 62, 'USA': 56, 'MEX': 71, 'BRA': 71, 'LVS': 50,
        'QAT': 57, 'ABU': 58
    }
    return LAPS.get(track_code.upper(), 50)
