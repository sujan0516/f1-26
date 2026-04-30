import re
import logging
from datetime import datetime, timezone
from typing import Any
from .config import JOLPICA, OPENF1, CURRENT_F1_YEAR, TEAM_ORDER_DEFAULT
from .http_client import safe_http_json
from .utils import normalize_driver_name, canonical_team_name, normalize_driver_standings, normalize_constructors_standings, ordinal_pos, parse_iso_datetime
from .constants import DRIVER_ID_MAP, CIRCUIT_ID_MAP

logger = logging.getLogger('f1_app')

def merge_race_schedule_from_results(race_schedule: list[dict[str, Any]], races: list[dict[str, Any]]) -> list[dict[str, Any]]:
    schedule = [dict(r) for r in (race_schedule or [])]
    completed = set()
    for race in races or []:
        code = CIRCUIT_ID_MAP.get((race.get('Circuit') or {}).get('circuitId') or '')
        if code:
            completed.add(code)
    if not schedule or not completed:
        return schedule
    found_next = False
    for r in schedule:
        if r.get('canc'):
            continue
        if r.get('n') in completed:
            r['done'] = True
            r.pop('next', None)
        elif not found_next:
            r['next'] = True
            found_next = True
            r.pop('done', None)
        else:
            r.pop('done', None)
            r.pop('next', None)
    return schedule

def blend_reliability(races: list[dict[str, Any]], priors: dict[str, float], race_schedule: list[dict[str, Any]]) -> dict[str, float]:
    if not races:
        return priors
    total = max(sum(1 for r in race_schedule if not r.get('canc')), 1)
    driver_race_count: dict[str, int] = {}
    driver_dnf_count: dict[str, int] = {}
    for race in races:
        for r in race.get('Results') or []:
            driver = r.get('Driver') or {}
            did = driver.get('driverId')
            if not did:
                continue
            driver_race_count[did] = driver_race_count.get(did, 0) + 1
            status = str(r.get('status') or '')
            if not re.match(r'^Finished$|^\+\d+ Lap', status):
                driver_dnf_count[did] = driver_dnf_count.get(did, 0) + 1
    race_fraction = len(races) / total
    live_weight = race_fraction * race_fraction * (3 - 2 * race_fraction)
    out = {}
    for did, count in driver_race_count.items():
        name = DRIVER_ID_MAP.get(did)
        if not name:
            continue
        dnfs = driver_dnf_count.get(did, 0)
        live_rel = max(1 - (dnfs / max(count, 1)), 0.50)
        prior = float(priors.get(name, 0.93))
        out[name] = round(prior * (1 - live_weight) + live_rel * live_weight, 3)
    
    # Fill in priors for drivers not in the recent races
    for name, prior in priors.items():
        if name not in out:
            out[name] = prior
            
    return out

def build_live_2026_stats_backend(payload: dict[str, Any]) -> dict[str, Any]:
    race_schedule = payload.get('raceSchedule') or []
    reliability_priors = payload.get('reliabilityPriors') or payload.get('reliability') or {}
    stand_json = safe_http_json(f'{JOLPICA}/{CURRENT_F1_YEAR}/driverStandings.json', timeout=7.0)
    results_json = safe_http_json(f'{JOLPICA}/{CURRENT_F1_YEAR}/results.json?limit=500', timeout=7.0)
    qual_json = safe_http_json(f'{JOLPICA}/{CURRENT_F1_YEAR}/qualifying.json?limit=500', timeout=7.0)
    sprint_json = safe_http_json(f'{JOLPICA}/{CURRENT_F1_YEAR}/sprint.json?limit=200', timeout=7.0)

    standings = (((stand_json or {}).get('MRData') or {}).get('StandingsTable') or {}).get('StandingsLists') or []
    standings = (standings[0] or {}).get('DriverStandings') if standings else []
    races = (((results_json or {}).get('MRData') or {}).get('RaceTable') or {}).get('Races') or []
    quals = (((qual_json or {}).get('MRData') or {}).get('RaceTable') or {}).get('Races') or []
    sprints = (((sprint_json or {}).get('MRData') or {}).get('RaceTable') or {}).get('Races') or []

    driver_stats: dict[str, dict[str, int]] = {}
    driver_meta: dict[str, dict[str, str]] = {}
    driver_starts: dict[str, int] = {}
    for race in races:
        for r in race.get('Results') or []:
            driver = r.get('Driver') or {}
            did = driver.get('driverId')
            if not did:
                continue
            if did not in driver_stats:
                driver_stats[did] = {'wins': 0, 'pods': 0, 'dnfs': 0, 'fastestLaps': 0}
            pos = int(r.get('position') or 0)
            status = str(r.get('status') or '')
            if pos == 1:
                driver_stats[did]['wins'] += 1
            if 1 <= pos <= 3:
                driver_stats[did]['pods'] += 1
            if not re.match(r'^Finished$|^\+\d+ Lap', status):
                driver_stats[did]['dnfs'] += 1
            
            fl = r.get('FastestLap') or {}
            if str(fl.get('rank')) == '1':
                driver_stats[did]['fastestLaps'] += 1

            driver_starts[did] = driver_starts.get(did, 0) + 1
            driver_meta[did] = {'givenName': driver.get('givenName') or '', 'familyName': driver.get('familyName') or ''}

    poles_map: dict[str, int] = {}
    for race in quals:
        results = race.get('QualifyingResults') or []
        if results:
            pole = results[0]
            driver = (pole or {}).get('Driver') or {}
            did = driver.get('driverId')
            if did:
                poles_map[did] = poles_map.get(did, 0) + 1
                driver_meta.setdefault(did, {'givenName': driver.get('givenName') or '', 'familyName': driver.get('familyName') or ''})

    standing_map: dict[str, dict[str, Any]] = {}
    for s in standings or []:
        driver = s.get('Driver') or {}
        did = driver.get('driverId')
        if not did:
            continue
        standing_map[did] = s
        driver_meta[did] = {'givenName': driver.get('givenName') or '', 'familyName': driver.get('familyName') or ''}

    driver_ids = set(driver_stats) | set(poles_map) | set(standing_map)
    stats_by_id: dict[str, dict[str, Any]] = {}
    for did in driver_ids:
        st = standing_map.get(did) or {}
        meta = driver_meta.get(did) or {}
        base = driver_stats.get(did) or {'wins': 0, 'pods': 0, 'dnfs': 0, 'fastestLaps': 0}
        stats_by_id[did] = {
            'fullName': ' '.join(x for x in [meta.get('givenName'), meta.get('familyName')] if x).strip(),
            'pos': ordinal_pos((st or {}).get('position')),
            'pts': int(float((st or {}).get('points') or 0)) if (st or {}).get('points') is not None else None,
            'wins': base['wins'],
            'pod': base['pods'],
            'poles': poles_map.get(did, 0),
            'dnf': base['dnfs'],
            'fastestLaps': base['fastestLaps'],
            'starts': driver_starts.get(did, 0),
        }

    reliability = blend_reliability(races, reliability_priors, race_schedule)
    merged_schedule = merge_race_schedule_from_results(race_schedule, races)
    return {
        'ok': True,
        'statsById': stats_by_id,
        'reliability': reliability,
        'raceSchedule': merged_schedule,
        'resultsCount': len(races),
        'qualifyingCount': len(quals),
        'sprintCount': len(sprints),
        'hasLiveStats': bool(stats_by_id),
    }

def get_standings_data():
    live_drivers: list[dict[str, Any]] = []
    live_constructors: list[dict[str, Any]] = []
    got_any = False
    status_openf1 = 'loading'
    status_ergast = 'loading'
    badge_text = 'CACHED'
    badge_live = False
    source_provider = 'fallback'
    
    reached_openf1 = False
    reached_ergast = False

    try:
        sessions_data = safe_http_json(f'{OPENF1}/sessions?year={CURRENT_F1_YEAR}&session_type=Race', timeout=8.0)
        if sessions_data is not None:
            reached_openf1 = True
            sessions = sessions_data or []
        else:
            sessions = []

        sessions_sorted = sorted(sessions, key=lambda s: s.get('date_start', ''), reverse=True)
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
            c_data = safe_http_json(f'{OPENF1}/championship_teams?session_key={sk}', timeout=6.0, use_cache=True)
            
            if d_data is None and c_data is None:
                continue
            
            valid_sk_found = True
            d_data = d_data or []
            c_data = c_data or []
            
            if not d_data and not c_data:
                continue

            drivers_meta = safe_http_json(f'{OPENF1}/drivers?session_key={sk}', timeout=6.0, use_cache=True) or []
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
                break 
        
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
    return {
        'ok': True,
        'liveDrivers': live_drivers,
        'liveConstructors': live_constructors,
        'statusOpenF1': status_openf1,
        'statusErgast': status_ergast,
        'badgeText': badge_text,
        'badgeLive': badge_live,
        'sourceProvider': source_provider,
    }
