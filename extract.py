import ast
import re

with open('app.py.bak', 'r') as f:
    source = f.read()

tree = ast.parse(source)

funcs_to_extract = {
    'calculate_driver_radar',
    'build_team_analysis',
    'build_live_race_prediction_backend',
    'build_load_standings_backend',
    'build_race_strategy_timeline_backend',
    'build_telemetry_h2h_backend',
    'default_dynamic_bios',
    'load_dynamic_bios',
    'save_dynamic_bios',
    'build_session_bio_updates',
    'session_type_label',
    'meeting_label',
    'latest_position_by_driver',
    'best_lap_by_driver',
    'position_text',
    'format_lap_time',
    'generate_team_insights',
    'find_constructor_entry',
    'team_drivers_for',
    'esc',
    'build_pace_model',
    'get_deg_rate',
    '_box_muller_normal',
    'latest_completed_weekend_session',
    'latest_session_from_list',
    'build_race_strategy_timeline',
    'build_projected_strategy_fallback',
    'transcribe_audio_url'
}

routes_to_extract = {
    '/api/circuit-brief',
    '/api/driver-radar',
    '/api/team-analysis',
    '/api/load-standings',
    '/api/live-race-prediction',
    '/api/live-session',
    '/api/current-race-session',
    '/api/race-strategy-timeline',
    '/api/driver-headshots',
    '/api/transcribe-radio',
    '/api/h2h-telemetry',
    '/api/dynamic-bios',
    '/api/update-bios',
    '/api/backtest'
}

out_code = [
    "from __future__ import annotations",
    "from flask import Blueprint, request, jsonify",
    "from typing import Any, Optional, Dict, List",
    "import json, math, random, time",
    "from datetime import datetime, timedelta, timezone",
    "import html",
    "import numpy as np",
    "from pathlib import Path",
    "from .config import DATA_DIR, CURRENT_F1_YEAR, DRIVER_HEADSHOT_OVERRIDES, OPENF1, JOLPICA, TEAM_ORDER_DEFAULT",
    "from .http_client import safe_http_json",
    "from .cache import API_CACHE",
    "from .sessions import latest_race_session_backend, live_driver_team_map_for_session",
    "from .constants import TYRE_PACE_DEFAULT, TYRE_COLORS_DEFAULT, CIRCUIT_OVERTAKE_DEFAULT",
    "from .utils import canonical_team_name, get_tc, get_team_logo, normalize_driver_standings, normalize_constructors_standings, parse_iso_datetime, normalize_driver_name",
    "from .weather import build_weather_backend",
    "\nlegacy_api = Blueprint('legacy', __name__)\n",
    "DYNAMIC_BIOS_PATH = Path(DATA_DIR) / 'dynamic_bios.json'\n"
]

match = re.search(r'^CIRCUIT_TECH_BRIEFS = \{.*?^\}', source, re.MULTILINE | re.DOTALL)
if match: out_code.append(match.group(0))

for node in tree.body:
    if isinstance(node, ast.FunctionDef):
        if node.name in funcs_to_extract:
            func_source = ast.get_source_segment(source, node)
            out_code.append(func_source)
        
        is_route = False
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Attribute) and decorator.func.value.id == 'app':
                    if decorator.args and isinstance(decorator.args[0], ast.Constant):
                        if decorator.args[0].value in routes_to_extract:
                            is_route = True
        
        if is_route:
            func_source = ast.get_source_segment(source, node)
            func_source = re.sub(r'@app\.', '@legacy_api.', func_source)
            out_code.append(func_source)

with open('f1_app/legacy.py', 'w') as f:
    f.write("\n\n".join(out_code))
