from __future__ import annotations

import math
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .cache import API_CACHE
from .config import OPENF1
from .http_client import safe_http_json
from .sessions import latest_race_session_backend
from .track_codes import get_track_code_from_session


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_points_with_bounds(rows: List[Dict[str, Any]], bounds: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize raw OpenF1 x/y coordinates to px/py pixel space."""
    min_x = float(bounds.get("minX") or 0)
    max_x = float(bounds.get("maxX") or 1)
    min_y = float(bounds.get("minY") or 0)
    max_y = float(bounds.get("maxY") or 1)
    width = float(bounds.get("width") or 1000)
    height = float(bounds.get("height") or 700)
    pad = float(bounds.get("pad") or 50)

    dx = max(max_x - min_x, 1.0)
    dy = max(max_y - min_y, 1.0)
    inner_w = max(width - pad * 2, 1.0)
    inner_h = max(height - pad * 2, 1.0)

    cars = []
    for row in rows:
        try:
            x = float(row.get("x"))
            y = float(row.get("y"))
        except Exception:
            continue

        px = pad + ((x - min_x) / dx) * inner_w
        py = pad + (1.0 - ((y - min_y) / dy)) * inner_h

        cars.append({
            "driverNumber": row.get("driver_number"),
            "x": x,
            "y": y,
            "px": round(max(0, min(width, px)), 2),
            "py": round(max(0, min(height, py)), 2),
            "date": row.get("date"),
        })
    return cars


def latest_location_by_driver(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest: Dict[Any, Dict[str, Any]] = {}
    for row in rows or []:
        dn = row.get("driver_number")
        if dn is None:
            continue
        prev = latest.get(dn)
        if prev is None or str(row.get("date") or "") > str(prev.get("date") or ""):
            latest[dn] = row
    return list(latest.values())


def normalize_track_points(
    rows: List[Dict[str, Any]], width: int = 1000, height: int = 700, pad: int = 50
) -> Dict[str, Any]:
    """Compute bounds from raw rows and return normalized px/py points."""
    raw = []
    for r in rows or []:
        try:
            x = float(r.get("x"))
            y = float(r.get("y"))
        except Exception:
            continue
        if math.isfinite(x) and math.isfinite(y):
            raw.append({
                "x": x,
                "y": y,
                "driver_number": r.get("driver_number"),
                "date": r.get("date"),
            })

    if not raw:
        return {"ok": False, "points": [], "bounds": None}

    xs = [p["x"] for p in raw]
    ys = [p["y"] for p in raw]
    bounds = {
        "minX": min(xs), "maxX": max(xs),
        "minY": min(ys), "maxY": max(ys),
        "width": width, "height": height, "pad": pad,
    }
    points = normalize_points_with_bounds(raw, bounds)
    return {"ok": True, "points": points, "bounds": bounds}


def sort_track_points_for_outline(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not points:
        return []
    cx = sum(float(p["px"]) for p in points) / len(points)
    cy = sum(float(p["py"]) for p in points) / len(points)
    return sorted(points, key=lambda p: math.atan2(float(p["py"]) - cy, float(p["px"]) - cx))


def simplify_track_points(points: List[Dict[str, Any]], max_points: int = 350) -> List[Dict[str, Any]]:
    if len(points) <= max_points:
        return points
    step = max(1, math.ceil(len(points) / max_points))
    return points[::step]


def build_track_shape_backend(track_code: Optional[str] = None) -> Dict[str, Any]:
    from .track_codes import normalize_track_code
    requested_track = normalize_track_code(track_code or "MIA")

    session, is_live = latest_race_session_backend()

    if not session or not session.get("session_key"):
        return {
            "ok": False,
            "trackCode": requested_track,
            "source": "no-session",
            "points": [],
            "staticFallbackPath": f"/tracks/{requested_track}.svg",
        }

    sk = session.get("session_key")
    resolved_track = get_track_code_from_session(session) or requested_track

    cache_key = f"track-shape:{sk}:{resolved_track}"
    cached = API_CACHE.get(cache_key)
    if cached is not None:
        cached["cachedFrame"] = True
        return cached

    lookback = datetime.now(timezone.utc) - timedelta(minutes=20)
    anchor_q = urllib.parse.quote(iso_utc(lookback), safe="")

    rows = safe_http_json(
        f"{OPENF1}/location?session_key={sk}&date>={anchor_q}",
        timeout=8.0,
        ttl=60.0,
    ) or []

    norm = normalize_track_points(rows)
    if not norm.get("ok"):
        return {
            "ok": False,
            "sessionKey": sk,
            "trackCode": resolved_track,
            "source": "no-openf1-location-history",
            "points": [],
            "staticFallbackPath": f"/tracks/{resolved_track}.svg",
        }

    outline = sort_track_points_for_outline(norm["points"])
    outline = simplify_track_points(outline, max_points=350)

    result = {
        "ok": True,
        "isLive": is_live,
        "sessionKey": sk,
        "trackCode": resolved_track,
        "source": "openf1-location-history",
        "generatedAt": time.time(),
        "cachedFrame": False,
        "viewBox": {"width": 1000, "height": 700},
        "bounds": norm.get("bounds"),
        "points": outline,
    }

    API_CACHE.set(cache_key, result, ttl=60.0)
    return result


def build_live_location_backend() -> Dict[str, Any]:
    session, is_live = latest_race_session_backend()

    if not session or not session.get("session_key"):
        return {
            "ok": False,
            "error": "No live or recent race session found",
            "cars": [],
            "generatedAt": time.time(),
        }

    sk = session.get("session_key")
    track_code = get_track_code_from_session(session)

    cache_key = f"live-location:{sk}"
    cached = API_CACHE.get(cache_key)
    if cached is not None:
        cached["cachedFrame"] = True
        return cached

    lookback = datetime.now(timezone.utc) - timedelta(seconds=8)
    anchor_q = urllib.parse.quote(iso_utc(lookback), safe="")

    rows = safe_http_json(
        f"{OPENF1}/location?session_key={sk}&date>={anchor_q}",
        timeout=5.0,
        ttl=2.0,
    ) or []

    latest_rows = latest_location_by_driver(rows)

    # Try to use the stable track shape bounds for consistent coordinate mapping
    shape = build_track_shape_backend(track_code=track_code)
    bounds = shape.get("bounds") if shape and shape.get("ok") else None

    if bounds:
        cars = normalize_points_with_bounds(latest_rows, bounds)
        confidence = "HIGH"
    else:
        norm = normalize_track_points(latest_rows)
        cars = norm.get("points") or []
        confidence = "LOW_FRAME_NORMALIZED"

    result = {
        "ok": True,
        "isLive": is_live,
        "sessionKey": sk,
        "trackCode": track_code,
        "source": "openf1-location",
        "generatedAt": time.time(),
        "cachedFrame": False,
        "trackShapeAvailable": bool(bounds),
        "coordinateConfidence": confidence,
        "cars": cars,
    }

    API_CACHE.set(cache_key, result, ttl=2.0)
    return result
