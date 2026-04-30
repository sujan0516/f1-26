import time
from typing import Any
from .tyres import build_tyre_strategy_backend, undercut_status_label


def pit_action_rank(action: str) -> int:
    a = str(action or "").upper()
    if a == "BOX NOW": return 1
    if a == "ATTACK UNDERCUT": return 2
    if a == "PIT WINDOW OPEN": return 3
    if a == "PREPARE": return 4
    if a == "EXTEND": return 5
    return 9


def priority_score_for_pit_prediction(row: dict[str, Any]) -> int:
    pit = row.get("pitWindow") or {}
    undercut = row.get("undercut") or {}
    urgency = str(pit.get("urgency") or "").upper()
    score = 0
    if urgency == "BOX NOW": score += 100
    elif urgency == "PIT WINDOW OPEN": score += 70
    elif urgency == "PREPARE PIT WINDOW": score += 40
    else: score += 10
    if undercut.get("viable"): score += 30
    life = row.get("lifeRemaining")
    if life is not None:
        try:
            l = int(life)
            if l <= 2: score += 30
            elif l <= 5: score += 15
        except Exception:
            pass
    return score


def build_pit_summary(row: dict[str, Any], action: str) -> str:
    name = row.get("name") or "Driver"
    compound = row.get("compound") or "UNKNOWN"
    next_c = row.get("recommendedCompound") or "UNKNOWN"
    life = row.get("lifeRemaining")
    undercut = row.get("undercut") or {}
    parts = []
    if life is not None: parts.append(f"{life} laps life left")
    if undercut.get("viable"): parts.append("undercut window is open")
    return f"{name}: {action}. {compound} to {next_c}. Reason: {', '.join(parts) or 'stable stint'}."


def pit_confidence(row: dict[str, Any]) -> str:
    if row.get("isProjected") or str((row.get("undercut") or {}).get("status") or "").upper() == "PROJECTED":
        return "PROJECTED"
    if row.get("gapAhead") is None: return "LOW"
    return "MEDIUM"


def build_pit_predictor_backend(track_code: str = "MIA", simulate_rain: bool = False) -> dict[str, Any]:
    tyre_data = build_tyre_strategy_backend(track_code=track_code, simulate_rain=simulate_rain)
    if not tyre_data or not tyre_data.get("ok"):
        return {
            "ok": True,
            "isLive": False,
            "isProjected": True,
            "trackCode": track_code,
            "currentLap": 1,
            "totalLaps": 57,
            "mode": "PROJECTED",
            "dataSourceLabel": "PROJECTED",
            "dataQuality": {"mode": "PROJECTED", "confidence": "LOW"},
            "message": "Using projected fallback.",
            "recommendations": [],
            "topActions": {"boxNow": [], "undercut": [], "extend": []},
            "generatedAt": time.time(),
        }

    rows = []
    for r in tyre_data.get("recommendations") or []:
        pit = r.get("pitWindow") or {}
        undercut = r.get("undercut") or {}
        urgency = str(pit.get("urgency") or "").upper()
        if urgency == "BOX NOW": action = "BOX NOW"
        elif undercut.get("viable"): action = "ATTACK UNDERCUT"
        elif urgency == "PIT WINDOW OPEN": action = "PIT WINDOW OPEN"
        elif urgency == "PREPARE PIT WINDOW": action = "PREPARE"
        else: action = "EXTEND"

        rows.append({
            **r,
            "action": action,
            "priorityScore": priority_score_for_pit_prediction(r),
            "summary": build_pit_summary(r, action),
            "confidence": pit_confidence(r),
            "undercutStatus": undercut_status_label(undercut),
        })

    rows.sort(key=lambda x: (pit_action_rank(x["action"]), -x["priorityScore"]))

    return {
        "ok": True,
        "isLive": tyre_data.get("isLive"),
        "isProjected": tyre_data.get("isProjected", False),
        "sessionKey": tyre_data.get("sessionKey"),
        "trackCode": track_code,
        "currentLap": tyre_data.get("currentLap"),
        "totalLaps": tyre_data.get("totalLaps"),
        "trackWear": tyre_data.get("trackWear"),
        "rainPct": tyre_data.get("rainPct"),
        "mode": tyre_data.get("mode"),
        "dataSourceLabel": data_source_label(tyre_data),
        "safetyCarWindow": tyre_data.get("safetyCarWindow"),
        "dataQuality": tyre_data.get("dataQuality") or {
            "mode": "LIVE" if tyre_data.get("isLive") else "RECENT",
            "confidence": "MEDIUM",
        },
        "generatedAt": time.time(),
        "recommendations": rows,
        "topActions": {
            "boxNow": [r for r in rows if r["action"] == "BOX NOW"],
            "undercut": [r for r in rows if r["action"] == "ATTACK UNDERCUT"],
            "extend": [r for r in rows if r["action"] == "EXTEND"],
        },
    }


def data_source_label(payload: dict[str, Any]) -> str:
    if payload.get("isLive"):
        return "LIVE"
    if payload.get("isProjected") or payload.get("isPredicted"):
        return "PROJECTED"
    quality = payload.get("dataQuality") or {}
    return str(quality.get("mode") or payload.get("mode") or "RECENT").upper()


def group_projected_strategy_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    passthrough: list[dict[str, Any]] = []

    for event in events:
        if event.get("type") != "pit-window" or not str(event.get("title") or "").lower().endswith("projected first stop window"):
            passthrough.append(event)
            continue

        key = (
            event.get("lapStart"),
            event.get("lapEnd"),
            event.get("compoundFrom"),
            event.get("compoundTo"),
            event.get("severity"),
        )
        item = grouped.setdefault(key, {
            "lapStart": event.get("lapStart"),
            "lapEnd": event.get("lapEnd"),
            "title": "Projected first stop window",
            "type": "pit-window",
            "severity": event.get("severity") or "low",
            "description": "",
            "drivers": [],
            "teams": [],
            "compoundFrom": event.get("compoundFrom"),
            "compoundTo": event.get("compoundTo"),
        })
        item["drivers"].extend(event.get("drivers") or [])
        item["teams"].extend(event.get("teams") or [])

    for item in grouped.values():
        drivers = sorted({d for d in item["drivers"] if d})
        teams = sorted({t for t in item["teams"] if t})
        item["drivers"] = drivers
        item["teams"] = teams
        item["title"] = f"Projected first stop window · {len(drivers)} drivers"
        shown = ", ".join(drivers[:10])
        suffix = f" and {len(drivers) - 10} others" if len(drivers) > 10 else ""
        item["description"] = (
            f"{item.get('compoundFrom')} to {item.get('compoundTo')} projected stop window for "
            f"{shown}{suffix}. Live stint and interval data are not available yet."
        )
        passthrough.append(item)

    return passthrough


def build_race_strategy_timeline(track_code: str = "MIA", simulate_rain: bool = False) -> dict[str, Any]:
    """Build a chronological event timeline derived from live tyre strategy data."""
    tyre_data = build_tyre_strategy_backend(track_code=track_code, simulate_rain=simulate_rain)

    if not tyre_data or not tyre_data.get("ok"):
        return {
            "ok": True,
            "isLive": False,
            "isProjected": True,
            "trackCode": track_code,
            "mode": "PROJECTED STRATEGY",
            "dataSourceLabel": "PROJECTED",
            "events": [
                {
                    "lapStart": 1,
                    "lapEnd": 10,
                    "title": "Projected opening phase",
                    "type": "stint",
                    "severity": "low",
                    "description": "Waiting for live race data. Strategy is projected.",
                    "drivers": [],
                    "teams": [],
                    "compoundFrom": None,
                    "compoundTo": None,
                }
            ],
            "generatedAt": time.time(),
            "dataQuality": {
                "mode": "PROJECTED",
                "confidence": "LOW",
                "hasStints": False,
                "hasIntervals": False,
                "hasLaps": False,
                "hasWeather": False,
            },
        }

    events = []
    current_lap = tyre_data.get("currentLap", 1)
    total_laps = tyre_data.get("totalLaps", 57)

    for r in tyre_data.get("recommendations") or []:
        pit = r.get("pitWindow") or {}
        undercut = r.get("undercut") or {}
        name = r.get("name") or "Driver"
        urgency = str(pit.get("urgency") or "").upper()

        if urgency == "BOX NOW":
            events.append({
                "lapStart": current_lap,
                "lapEnd": current_lap,
                "title": f"{name}: Box now",
                "type": "pit-window",
                "severity": "critical",
                "description": f"{name} should box this lap based on tyre life and current strategy window.",
                "drivers": [name],
                "teams": [r.get("team")] if r.get("team") else [],
                "compoundFrom": r.get("compound"),
                "compoundTo": r.get("recommendedCompound"),
            })
        elif undercut.get("viable"):
            events.append({
                "lapStart": current_lap,
                "lapEnd": current_lap + 3,
                "title": f"{name}: Undercut opportunity",
                "type": "undercut",
                "severity": "high",
                "description": undercut.get("reason") or "Undercut window appears viable.",
                "drivers": [name],
                "teams": [r.get("team")] if r.get("team") else [],
                "compoundFrom": r.get("compound"),
                "compoundTo": r.get("recommendedCompound"),
            })
        elif tyre_data.get("isProjected"):
            pit_in = int(pit.get("recommendedInLaps") or 16)
            lap_start = max(1, min(int(total_laps), int(current_lap) + max(0, pit_in - 2)))
            lap_end = max(lap_start, min(int(total_laps), int(current_lap) + pit_in + 4))
            events.append({
                "lapStart": lap_start,
                "lapEnd": lap_end,
                "title": f"{name}: projected first stop window",
                "type": "pit-window",
                "severity": "low",
                "description": f"Projected {r.get('compound')} to {r.get('recommendedCompound')} stop window. Live stint and interval data are not available yet.",
                "drivers": [name],
                "teams": [r.get("team")] if r.get("team") else [],
                "compoundFrom": r.get("compound"),
                "compoundTo": r.get("recommendedCompound"),
            })
        elif urgency in {"PIT WINDOW OPEN", "PREPARE PIT WINDOW", "EXTEND STINT"}:
            pit_in = int(pit.get("recommendedInLaps") or 0)
            life_left = int(r.get("lifeRemaining") or 0)
            lap_start = max(int(current_lap), min(int(total_laps), int(current_lap) + max(0, pit_in - 2)))
            lap_end = max(lap_start, min(int(total_laps), int(current_lap) + max(pit_in + 3, min(life_left, 10))))
            is_extend = urgency == "EXTEND STINT"
            events.append({
                "lapStart": lap_start,
                "lapEnd": lap_end,
                "title": f"{name}: {urgency.lower()}",
                "type": "extend" if is_extend else "pit-window",
                "severity": "low" if is_extend else "medium",
                "description": (
                    f"{name} can extend the current {r.get('compound')} stint."
                    if is_extend
                    else f"{name} is approaching a {r.get('compound')} to {r.get('recommendedCompound')} pit window."
                ),
                "drivers": [name],
                "teams": [r.get("team")] if r.get("team") else [],
                "compoundFrom": r.get("compound"),
                "compoundTo": r.get("recommendedCompound"),
            })

    if not events:
        events.append({
            "lapStart": current_lap,
            "lapEnd": current_lap + 10,
            "title": "Stable strategy phase",
            "type": "extend",
            "severity": "low",
            "description": "No critical box-now or undercut event is active.",
            "drivers": [],
            "teams": [],
            "compoundFrom": None,
            "compoundTo": None,
        })

    if tyre_data.get("isProjected"):
        events = group_projected_strategy_events(events)
        projected_starts = [
            int(e.get("lapStart") or 1)
            for e in events
            if e.get("type") == "pit-window" and int(e.get("lapStart") or 1) > 1
        ]
        first_window_start = min(projected_starts) if projected_starts else min(int(total_laps), 14)
        opening_end = max(1, first_window_start - 1)
        events.insert(0, {
            "lapStart": 1,
            "lapEnd": opening_end,
            "title": "Projected opening stint",
            "type": "stint",
            "severity": "low",
            "description": "Projected opening phase before the first planned stop window. Drivers are expected to manage tyres and protect track position.",
            "drivers": [],
            "teams": [],
            "compoundFrom": None,
            "compoundTo": None,
        })

    return {
        "ok": True,
        "isLive": tyre_data.get("isLive", False),
        "isProjected": tyre_data.get("isProjected", False),
        "sessionKey": tyre_data.get("sessionKey"),
        "trackCode": track_code,
        "currentLap": current_lap,
        "totalLaps": total_laps,
        "trackWear": tyre_data.get("trackWear"),
        "rainPct": tyre_data.get("rainPct"),
        "mode": tyre_data.get("mode"),
        "dataSourceLabel": data_source_label(tyre_data),
        "safetyCarWindow": tyre_data.get("safetyCarWindow"),
        "events": events,
        "generatedAt": time.time(),
        "dataQuality": tyre_data.get("dataQuality") or {
            "mode": "LIVE" if tyre_data.get("isLive") else "RECENT",
            "confidence": "MEDIUM",
        },
    }
