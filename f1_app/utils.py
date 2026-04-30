import re
import math
import html
from datetime import datetime, timezone
from typing import Any, Optional, Union, List, Dict, Tuple
from .config import TEAM_ORDER_DEFAULT, TEAM_COLORS, DRIVER_HEADSHOT_OVERRIDES

def normalize_driver_name(name: Any) -> str:
    if not name: return 'Unknown'
    s = str(name).strip()
    s = re.sub(r'\s+', ' ', s)
    # Handle "Verstappen, Max" -> "Max Verstappen"
    if ',' in s:
        parts = [p.strip() for p in s.split(',')]
        if len(parts) == 2:
            s = f"{parts[1]} {parts[0]}"
    return s

def team_key(name: str = '') -> str:
    s = str(name or '').lower()
    replacements = [
        ('scuderia ', ''), ('formula 1 team', ''), ('f1 team', ''), ('team', ''),
        ('amg petronas', 'mercedes'), ('petronas', ''), ('oracle ', ''),
        ('red bull racing', 'red bull'), ('aston martin aramco', 'aston martin'),
        ('visa cash app racing bulls', 'racing bulls'), ('visa cash app rb', 'racing bulls'),
        ('visa cash app ', ''), ('cash app ', ''), ('kick sauber ferrari', 'audi'),
        ('stake sauber ferrari', 'audi'), ('sauber ferrari', 'audi'), ('stake f1 team kick sauber', 'audi'),
        ('kick sauber', 'audi'), ('stake sauber', 'audi'), ('atlassian ', ''), ('williams racing', 'williams'),
        ('bwt ', ''), ('tgr ', ''), ('visa ', ''), (' hp', '')
    ]
    for old, new in replacements:
        s = s.replace(old, new)
    s = s.replace(' rb ', ' racing bulls ')
    words = s.split()
    words = ['racing bulls' if w == 'rb' else 'audi' if w == 'sauber' else w for w in words]
    return ' '.join(' '.join(words).split()).strip()

def canonical_team_name(name: str = '', team_order: Optional[List[str]] = None) -> str:
    if team_order is None:
        team_order = TEAM_ORDER_DEFAULT
    raw = str(name or '').strip()
    if not raw:
        return 'Unknown'
    key = team_key(raw)
    checks = [
        ('racing bulls', 'Racing Bulls'), ('red bull', 'Red Bull'), ('mercedes', 'Mercedes'),
        ('audi', 'Audi'), ('ferrari', 'Ferrari'), ('mclaren', 'McLaren'), ('haas', 'Haas'),
        ('alpine', 'Alpine'), ('williams', 'Williams'), ('aston martin', 'Aston Martin'), ('cadillac', 'Cadillac')
    ]
    for needle, canonical in checks:
        if needle in key:
            return canonical
    for team in team_order:
        tkey = team_key(team)
        if key == tkey or key in tkey or tkey in key:
            return team
    return raw

def get_tc(name: str = '') -> str:
    key = str(name or '')
    for team, color in TEAM_COLORS.items():
        if team.lower() in key.lower():
            return color
    return '#5a6278'

def get_team_logo(team_name: str, size: int = 24) -> str:
    # This is still a bit coupled to HTML, but keeping for compatibility
    from .config import TEAM_LOGOS
    for k, v in TEAM_LOGOS.items():
        if k.lower() in str(team_name).lower():
            return f'<div style="width:{size}px;height:{size}px;background:#000;border-radius:4px;padding:2px;display:inline-flex;align-items:center;justify-content:center;margin-right:8px;vertical-align:middle;box-shadow:0 0 0 1px rgba(255,255,255,0.1);overflow:hidden;"><img src="{v}" style="max-width:100%;max-height:100%;object-fit:contain;" alt="{k}"></div>'
    return ""

def parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not value: return None
    try:
        s = str(value).replace('Z', '+00:00')
        return datetime.fromisoformat(s)
    except Exception:
        return None

def parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    return parse_iso_datetime(value)

def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

def drs_state(value: Any) -> Tuple[str, str]:
    v = str(value or '')
    if v in {'1', '8', '10', '12', '14'}: return 'OM ACTIVE', 'var(--green)'
    return 'OM READY', 'var(--muted)'

def ordinal_pos(pos: Optional[Union[str, int]]) -> Optional[str]:
    if pos is None:
        return None
    p = str(pos)
    if p == '1':
        return '1st'
    if p == '2':
        return '2nd'
    if p == '3':
        return '3rd'
    return f'{p}th'

def parse_qual_time(t: Optional[str]) -> Optional[float]:
    if not t or not str(t).strip(): return None
    try:
        if ':' in t:
            m, s = t.split(':')
            return int(m)*60 + float(s)
        return float(t)
    except Exception:
        return None

def latest_by_key(rows: List[Dict[str, Any]], key: str) -> Dict[Any, Dict[str, Any]]:
    out = {}
    for r in rows:
        val = r.get(key)
        if val is None: continue
        prev = out.get(val)
        if prev is None or str(r.get('date', '')) > str(prev.get('date', '')):
            out[val] = r
    return out

def normalize_driver_standings(drivers: List[Dict[str, Any]], team_order: List[str]) -> List[Dict[str, Any]]:
    out = []
    for idx, entry in enumerate(drivers or []):
        out.append({
            **entry,
            'pos': int(float(entry.get('pos', idx + 1) or (idx + 1))),
            'pts': int(float(entry.get('pts', entry.get('points', 0)) or 0)),
            'team': canonical_team_name(entry.get('team') or entry.get('team_name') or '', team_order),
        })
    return out

def normalize_constructors_standings(constructors: List[Dict[str, Any]], team_order: List[str]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for idx, entry in enumerate(constructors or []):
        name = canonical_team_name(entry.get('name') or entry.get('team_name') or '', team_order)
        if not name:
            continue
        pts = int(float(entry.get('pts', entry.get('points', 0)) or 0))
        pos = int(float(entry.get('pos', entry.get('position', idx + 1)) or (idx + 1)))
        prev = merged.get(name)
        if prev is None or pts > prev['pts'] or (pts == prev['pts'] and pos < prev['pos']):
            merged[name] = {'name': name, 'pts': pts, 'pos': pos}
    arr = list(merged.values())
    arr.sort(key=lambda x: (-x['pts'], x['pos'], team_order.index(x['name']) if x['name'] in team_order else 999))
    for i, entry in enumerate(arr, start=1):
        entry['pos'] = i
    return arr
