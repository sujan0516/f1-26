import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from .config import OPENF1, CURRENT_F1_YEAR, TEAM_ORDER_DEFAULT
from .http_client import safe_http_json
from .utils import (
    normalize_driver_name, canonical_team_name, latest_by_key, 
    drs_state, get_tc, get_team_logo, parse_iso_dt, iso_utc,
    parse_iso_datetime
)
from .sessions import latest_race_session_backend
from .tyres import improved_undercut_model, undercut_status_label

logger = logging.getLogger('f1_app')

def esc(s: Any) -> str:
    return str(s).replace('<', '&lt;').replace('>', '&gt;')

def build_live_timing_backend() -> dict[str, Any]:
    sess, is_live = latest_race_session_backend()
    if not sess:
        return {'ok': False, 'error': 'No session found'}

    sk = sess.get('session_key')
    now = datetime.now(timezone.utc)
    lookback = now - timedelta(minutes=10)
    lookback_q = lookback.isoformat().replace('+00:00', 'Z')

    # Fetch data
    drivers = safe_http_json(f'{OPENF1}/drivers?session_key={sk}', timeout=6.0) or []
    intervals = safe_http_json(f'{OPENF1}/intervals?session_key={sk}&date>={lookback_q}', timeout=6.0) or []
    stints = safe_http_json(f'{OPENF1}/stints?session_key={sk}', timeout=6.0) or []
    rc = safe_http_json(f'{OPENF1}/race_control?session_key={sk}', timeout=6.0) or []
    
    # Process
    driver_map = {
        d.get('driver_number'): {
            'name': normalize_driver_name(d.get('full_name') or d.get('name_acronym')),
            'team': canonical_team_name(d.get('team_name') or '', TEAM_ORDER_DEFAULT),
            'acronym': d.get('name_acronym') or str(d.get('driver_number')),
            'color': d.get('team_colour') or '#ffffff'
        } for d in drivers
    }

    latest_intervals = latest_by_key(intervals, 'driver_number')
    latest_stints = latest_by_key(stints, 'driver_number')
    
    # Sort by gap to leader
    sorted_drivers = sorted(
        latest_intervals.values(), 
        key=lambda x: float(x.get('gap_to_leader') or 999)
    )

    rows_html = ""
    for idx, interval in enumerate(sorted_drivers):
        dn = interval.get('driver_number')
        d_info = driver_map.get(dn, {'name': f'#{dn}', 'team': 'Unknown', 'acronym': str(dn), 'color': '#fff'})
        stint = latest_stints.get(dn, {})
        
        gap = interval.get('gap_to_car_ahead') or '—'
        leader_gap = interval.get('gap_to_leader') or '—'
        
        # Build HTML for the row (Simplified but compatible)
        rows_html += f"""
        <div class="timing-row">
            <div class="timing-pos">{idx+1}</div>
            <div class="timing-driver" style="border-left: 3px solid {d_info['color']}">{d_info['acronym']}</div>
            <div class="timing-gap">{gap}</div>
            <div class="timing-interval">{leader_gap}</div>
            <div class="timing-stint">{stint.get('compound', '—')} ({stint.get('tyre_age_at_start', '0')})</div>
        </div>
        """

    # Race Control
    rc_html = ""
    for msg in sorted(rc, key=lambda x: x.get('date', ''), reverse=True)[:5]:
        m_text = msg.get('message') or ''
        m_date = parse_iso_dt(msg.get('date'))
        time_str = m_date.strftime('%H:%M:%S') if m_date else ''
        rc_html += f'<div class="rc-msg"><span class="rc-time">{time_str}</span> {esc(m_text)}</div>'

    return {
        'ok': True,
        'isLive': is_live,
        'sessionName': sess.get('session_name', 'Race'),
        'contentHtml': rows_html + '<div class="rc-wrap">' + rc_html + '</div>',
        'generatedAt': time.time()
    }

def build_live_qualifying_backend() -> dict[str, Any]:
    # Similar structure but for qualifying
    # For now, I'll return a placeholder to avoid 404
    return {'ok': True, 'contentHtml': '<div>Qualifying data coming soon...</div>'}
