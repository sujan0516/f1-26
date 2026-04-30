import time
import json
from pathlib import Path
from typing import Any
from flask import Blueprint, jsonify, request, Response

from .cache import SOURCE_HEALTH, API_CACHE
from .tyres import build_tyre_strategy_backend
from .strategy import build_pit_predictor_backend, build_race_strategy_timeline
from .track_map import build_track_shape_backend, build_live_location_backend
from .practice import build_practice_live_timing_backend
from .weather import build_weather_backend
from .standings import get_standings_data, build_live_2026_stats_backend
from .timing import build_live_timing_backend, build_live_qualifying_backend
from .telemetry import build_live_speed_backend, build_live_pace_backend, build_live_pitstops_backend
from .predictions import monte_carlo
from .config import HEAVY_LIVE_REFRESH_SECONDS, SPEED_REFRESH_SECONDS, OPENF1_HEAVY_FETCH_TTL, LOCATION_REFRESH_SECONDS, DATA_DIR

api = Blueprint("api", __name__)

@api.get("/api/routes")
def api_routes() -> Any:
    from flask import current_app
    routes = []
    for rule in current_app.url_map.iter_rules():
        routes.append({"rule": str(rule), "methods": sorted(list(rule.methods))})
    return jsonify({"ok": True, "routes": routes})

@api.get("/api/source-health")
def api_source_health() -> Any:
    return jsonify({"ok": True, "sources": SOURCE_HEALTH})

@api.get("/api/standings")
def api_standings() -> Any:
    return jsonify(get_standings_data())

@api.post("/api/live-2026-stats")
def api_live_2026_stats() -> Any:
    payload = request.json or {}
    return jsonify(build_live_2026_stats_backend(payload))

@api.get("/api/live-timing")
def api_live_timing() -> Any:
    # Use simple caching wrapper
    return jsonify(get_heavy_live_timing_cached())

@api.get("/api/live-qualifying")
def api_live_qualifying() -> Any:
    return jsonify(build_live_qualifying_backend())

@api.get("/api/live-speed")
def api_live_speed() -> Any:
    return jsonify(build_live_speed_backend())

@api.post("/api/live-pace")
def api_live_pace() -> Any:
    payload = request.json or {}
    return jsonify(build_live_pace_backend(payload))

@api.get("/api/live-pitstops")
def api_live_pitstops() -> Any:
    return jsonify(build_live_pitstops_backend())

@api.post("/api/monte-carlo")
def api_monte_carlo() -> Any:
    payload = request.json or {}
    return jsonify(monte_carlo(payload))

@api.get("/api/tyre-strategy")
def api_tyre_strategy() -> Any:
    track_code = str(request.args.get("trackCode") or "MIA").upper()
    simulate_rain = str(request.args.get("simulateRain") or "").lower() in {"1", "true", "yes", "on"}
    return jsonify(build_tyre_strategy_backend(track_code=track_code, simulate_rain=simulate_rain))

@api.get("/api/pit-predictor")
def api_pit_predictor() -> Any:
    track_code = str(request.args.get("trackCode") or "MIA").upper()
    simulate_rain = str(request.args.get("simulateRain") or "").lower() in {"1", "true", "yes", "on"}
    return jsonify(build_pit_predictor_backend(track_code=track_code, simulate_rain=simulate_rain))

@api.get("/api/track-shape")
def api_track_shape() -> Any:
    track_code = str(request.args.get("trackCode") or "MIA").upper()
    return jsonify(build_track_shape_backend(track_code=track_code))

@api.get("/api/live-location")
def api_live_location() -> Any:
    return jsonify(build_live_location_backend())

@api.get("/api/location-stream")
def api_location_stream() -> Any:
    """SSE stream for real-time car position updates. Frontend uses EventSource on this endpoint."""
    def event_stream():
        while True:
            try:
                data = build_live_location_backend()
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            except GeneratorExit:
                break
            except Exception as e:
                payload = {
                    "ok": False,
                    "error": str(e),
                    "cars": [],
                    "generatedAt": time.time(),
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            time.sleep(LOCATION_REFRESH_SECONDS)

    return Response(event_stream(), mimetype="text/event-stream")

@api.get("/api/practice-live-timing")
def api_practice_live_timing() -> Any:
    return jsonify(build_practice_live_timing_backend())

@api.get("/api/race-strategy-timeline")
def api_race_strategy_timeline() -> Any:
    track_code = str(request.args.get("trackCode") or "MIA").upper()
    simulate_rain = str(request.args.get("simulateRain") or "").lower() in {"1", "true", "yes", "on"}
    return jsonify(build_race_strategy_timeline(track_code=track_code, simulate_rain=simulate_rain))

@api.get("/api/weather")
def api_weather() -> Any:
    track_code = str(request.args.get("trackCode") or "MIA").upper()
    return jsonify(build_weather_backend(track_code=track_code))

@api.get("/api/stream")
def api_stream() -> Any:
    def event_stream():
        while True:
            data = get_heavy_live_timing_cached()
            yield f"data: {json.dumps(data)}\n\n"
            time.sleep(HEAVY_LIVE_REFRESH_SECONDS)
    return Response(event_stream(), mimetype='text/event-stream')

@api.get("/api/speed-stream")
def api_speed_stream() -> Any:
    def event_stream():
        while True:
            data = build_live_speed_backend()
            yield f"data: {json.dumps(data)}\n\n"
            time.sleep(SPEED_REFRESH_SECONDS)
    return Response(event_stream(), mimetype='text/event-stream')

def get_heavy_live_timing_cached() -> dict[str, Any]:
    # Simple caching logic to avoid hitting APIs too often
    cache_key = 'heavy-live-timing-frame'
    cached = API_CACHE.get(cache_key)
    if cached:
        cached['cachedFrame'] = True
        return cached
    
    data = build_live_timing_backend()
    if data.get('ok'):
        API_CACHE.set(cache_key, data, ttl=OPENF1_HEAVY_FETCH_TTL)
    return data

from .config import STATIC_DIR, TRACK_CODES

def count_track_svgs() -> dict:
    folder = STATIC_DIR / "tracks"
    return {code: (folder / f"{code}.svg").exists() for code in TRACK_CODES}

@api.get("/api/feature-health")
def api_feature_health():
    return jsonify({
        "ok": True,
        "checks": {
            "routes": {
                "tyreStrategy": True,
                "pitPredictor": True,
                "raceStrategyTimeline": True,
                "trackShape": True,
                "liveLocation": True,
                "locationStream": True,
                "practiceLiveTiming": True,
                "weather": True,
                "standings": True,
                "monteCarlo": True,
                "liveTiming": True,
                "appHealth": True
            },
            "assets": {
                "trackSvgs": count_track_svgs(),
            },
            "sources": SOURCE_HEALTH,
        }
    })


def panel_check(name: str, payload: dict[str, Any], required: list[str]) -> dict[str, Any]:
    missing = [key for key in required if key not in payload]
    return {
        "ok": bool(payload.get("ok")) and not missing,
        "name": name,
        "missing": missing,
        "mode": payload.get("mode") or payload.get("dataSourceLabel"),
        "count": len(payload.get("events") or payload.get("recommendations") or payload.get("drivers") or []),
    }


@api.get("/api/app-health")
def api_app_health() -> Any:
    track_code = str(request.args.get("trackCode") or "MIA").upper()
    checks = []

    weather = build_weather_backend(track_code)
    tyres = build_tyre_strategy_backend(track_code=track_code)
    timeline = build_race_strategy_timeline(track_code=track_code)
    pit = build_pit_predictor_backend(track_code=track_code)
    practice = build_practice_live_timing_backend()

    checks.append(panel_check("weather", weather, ["ok", "weather", "trackCode"]))
    checks.append(panel_check("tyres", tyres, ["ok", "recommendations", "mode", "trackCode"]))
    checks.append(panel_check("raceStrategyTimeline", timeline, ["ok", "events", "mode", "trackCode"]))
    checks.append(panel_check("pitPredictor", pit, ["ok", "recommendations", "mode", "trackCode"]))
    checks.append(panel_check("practice", practice, ["ok", "drivers", "dataAgeLabel"]))

    prediction_ok = True
    prediction_missing: list[str] = []
    try:
        boot = json.loads((Path(DATA_DIR) / "bootstrap_data.json").read_text())
        sample = monte_carlo({
            "drivers": boot.get("FB_DRIVERS") or [],
            "constructors": boot.get("FB_CONSTRUCTORS") or [],
            "runs": 1000,
            "raceSchedule": boot.get("RACE_SCHEDULE") or [],
            "reliability": boot.get("RELIABILITY_PRIORS") or {},
            "teamPace": boot.get("TEAM_PACE") or {},
            "driverSkill": boot.get("DRIVER_SKILL_PRIORS") or {},
        })
        prediction_missing = [
            key for key in ["ok", "champDriver", "champConstructor", "driverProbabilities", "constructorProbabilities"]
            if key not in sample
        ]
        prediction_ok = bool(sample.get("ok")) and not prediction_missing
    except Exception as e:
        prediction_ok = False
        prediction_missing = [str(e)]

    checks.append({
        "ok": prediction_ok,
        "name": "championshipPrediction",
        "missing": prediction_missing,
        "mode": "SIMULATION",
        "count": 0,
    })

    return jsonify({
        "ok": all(item["ok"] for item in checks),
        "trackCode": track_code,
        "checks": checks,
        "generatedAt": time.time(),
    })
