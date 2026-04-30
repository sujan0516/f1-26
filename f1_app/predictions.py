import logging
import numpy as np
from typing import Any
from .config import TEAM_ORDER_DEFAULT
from .utils import normalize_driver_standings, normalize_constructors_standings, canonical_team_name
from .constants import PTS_TABLE, SPRINT_PTS, CIRCUIT_OVERTAKE_DEFAULT
from .tyres import get_deg_rate

logger = logging.getLogger('f1_app')

ENGINE_MAP: dict[str, str] = {
    'Mercedes': 'Mercedes', 'McLaren': 'Mercedes', 'Williams': 'Mercedes',
    'Ferrari': 'Ferrari', 'Haas': 'Ferrari',
    'Red Bull': 'Ford', 'Racing Bulls': 'Ford',
    'Aston Martin': 'Honda',
    'Alpine': 'Alpine',
    'Audi': 'Audi', 
    'Cadillac': 'Cadillac',
}

DRIVER_CRASH_RISK: dict[str, float] = {
    'Max Verstappen': 0.10, 'Lewis Hamilton': 0.08, 'Charles Leclerc': 0.22,
    'Lando Norris': 0.15, 'George Russell': 0.14, 'Oscar Piastri': 0.12,
    'Carlos Sainz': 0.14, 'Fernando Alonso': 0.11, 'Kimi Antonelli': 0.28,
    'Isack Hadjar': 0.32, 'Arvid Lindblad': 0.35, 'Gabriel Bortoleto': 0.33,
    'Franco Colapinto': 0.36, 'Pierre Gasly': 0.17, 'Esteban Ocon': 0.19,
    'Oliver Bearman': 0.30, 'Liam Lawson': 0.25, 'Alexander Albon': 0.16,
    'Nico Hulkenberg': 0.15, 'Lance Stroll': 0.21, 'Valtteri Bottas': 0.14,
    'Sergio Perez': 0.18, 'Yuki Tsunoda': 0.26,
}

WET_KINGS: dict[str, float] = {
    'Max Verstappen': 1.12, 'Lewis Hamilton': 1.10, 'Fernando Alonso': 1.08,
    'Charles Leclerc': 1.04, 'Lando Norris': 1.03, 'George Russell': 1.03,
    'Oscar Piastri': 1.02, 'Pierre Gasly': 1.02, 'Carlos Sainz': 1.02,
}

def _box_muller_normal(shape: tuple[int, ...], rng: np.random.Generator) -> np.ndarray:
    u1 = rng.uniform(1e-10, 1.0, shape)
    u2 = rng.uniform(0.0, 1.0, shape)
    return np.sqrt(-2.0 * np.log(u1)) * np.cos(2.0 * np.pi * u2)

def build_pace_model(
    drivers: list[dict[str, Any]],
    race_schedule: list[dict[str, Any]],
    team_pace: dict[str, float],
    driver_skill: dict[str, float],
) -> np.ndarray:
    done = max(sum(1 for r in race_schedule if r.get('done')), 1)
    total = max(sum(1 for r in race_schedule if not r.get('canc')), 1)

    skill = np.array([float(driver_skill.get(d.get('name'), 0.70)) for d in drivers])
    team  = np.array([float(team_pace.get(d.get('team'), 0.55)) for d in drivers])
    form_raw = np.array([max(float(d.get('pts', 0)) / done, 0.5) / 25.0 for d in drivers])

    t = done / total
    evidence_weight = t * t * (3.0 - 2.0 * t)

    raw_prior = 0.65 + (skill * team - 0.35) * 0.6
    prior = raw_prior / (raw_prior.sum() or 1.0)

    flat_form = np.sqrt(form_raw)
    form = flat_form / (flat_form.sum() or 1.0)

    blended = prior * (1.0 - evidence_weight) + form * evidence_weight
    return blended / (blended.sum() or 1.0)

def _simulate_race_vectorised(
    pace: np.ndarray,
    driver_names: list[str],
    driver_teams: list[str],
    reliability: dict[str, float],
    circuit_overtake: float,
    safety_car_chance: float,
    rain_chance: float,
    runs: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(driver_names)
    pts_lookup = np.array(PTS_TABLE + [0] * max(n - len(PTS_TABLE), 0), dtype=np.int32)

    is_wet = rng.random(runs) < rain_chance
    wet_f  = is_wet.astype(np.float64)

    eff_sc_chance = np.where(is_wet, np.minimum(safety_car_chance + 0.25, 0.85), safety_car_chance)
    sc  = rng.random(runs) < eff_sc_chance
    vsc = (~sc) & (rng.random(runs) < np.where(is_wet, 0.30, 0.22))

    overtake_σ_scale = 0.75 + 0.25 * circuit_overtake
    sigma = np.where(is_wet, 0.35, np.where(sc, 0.22, np.where(vsc, 0.17, 0.15)))
    sigma = sigma * overtake_σ_scale / 3.0

    pace_noise = _box_muller_normal((runs, n), rng) * sigma[:, np.newaxis]

    wet_mult = np.array([WET_KINGS.get(nm, 0.98) for nm in driver_names])
    wet_mult_mat = 1.0 + wet_f[:, np.newaxis] * (wet_mult[np.newaxis, :] - 1.0)

    incident_hit   = rng.random((runs, n)) < np.where(is_wet, 0.12, 0.08)[:, np.newaxis]
    incident_delta = _box_muller_normal((runs, n), rng) * 0.1

    quali_noise = _box_muller_normal((runs, n), rng) * (sigma[:, np.newaxis] * 0.45)
    quali_pace = (pace[np.newaxis, :] + quali_noise) * wet_mult_mat
    
    grid_order = np.argsort(-quali_pace, axis=1, kind='stable')
    grid_pos = np.argsort(grid_order, axis=1, kind='stable')
    
    track_pos_factor = np.where(sc[:, np.newaxis], 0.2, 1.0)
    normalized_pos = 1.0 - (grid_pos / max((n - 1) / 2.0, 1.0))
    pos_bias = normalized_pos * 0.03
    
    dirty_air_severity = (1.0 - circuit_overtake) * 0.05
    dirty_air_penalty = np.where(grid_pos > 2, -dirty_air_severity, 0.0)
    grid_bonus = (pos_bias + dirty_air_penalty) * track_pos_factor

    race_pace = (pace[np.newaxis, :] + pace_noise) * wet_mult_mat
    race_pace += np.where(incident_hit, incident_delta, 0.0)
    race_pace += grid_bonus
    
    compounds = ['SOFT', 'MEDIUM', 'HARD']
    sim_tyres = rng.choice(compounds, size=(runs, n))
    tyre_penalties = np.zeros((runs, n))
    for c in compounds:
        mask = (sim_tyres == c)
        tyre_penalties[mask] = 22 * get_deg_rate(c) * 0.005
    race_pace -= tyre_penalties

    sc_mask = (sc | (is_wet & (rng.random(runs) < 0.5)))[:, np.newaxis]
    field_avg = race_pace.mean(axis=1, keepdims=True)
    race_pace = np.where(sc_mask, race_pace * 0.25 + field_avg * 0.75, race_pace)

    mech_surv = np.array([
        1.0 - (1.0 - float(reliability.get(nm, 0.93))) * 0.55
        for nm in driver_names
    ], dtype=np.float64)
    
    mech_prob  = 1.0 - mech_surv[np.newaxis, :]
    
    engine_list = [ENGINE_MAP.get(t, t) for t in driver_teams]
    unique_engines = list(set(engine_list))
    if unique_engines and unique_engines != ['']:
        engine_stress = rng.random((runs, len(unique_engines)))
        driver_engine_idx = np.array([unique_engines.index(e) for e in engine_list])
        driver_stress = engine_stress[:, driver_engine_idx]
        correlated_mech_prob = mech_prob + np.where(driver_stress > 0.96, 0.12, 0.0)
    else:
        correlated_mech_prob = mech_prob

    crash_base = np.array([
        DRIVER_CRASH_RISK.get(nm, 0.20) for nm in driver_names
    ], dtype=np.float64)
    wet_crash_scale = 1.0 + wet_f[:, np.newaxis] * 0.5
    crash_prob = np.clip(crash_base[np.newaxis, :] * 0.06 * wet_crash_scale, 0, 0.4)
    
    dnf_mask = (rng.random((runs, n)) < correlated_mech_prob) | (rng.random((runs, n)) < crash_prob)
    race_pace = np.where(dnf_mask, -1e9, race_pace)

    order = np.argsort(-race_pace, axis=1, kind='stable')
    pts_per_run = np.zeros((runs, n), dtype=np.int32)
    for pos_i in range(min(n, len(PTS_TABLE))):
        driver_at_pos = order[:, pos_i]
        scored = ~dnf_mask[np.arange(runs), driver_at_pos]
        pts_per_run[np.arange(runs), driver_at_pos] = np.where(
            scored, pts_lookup[pos_i], 0
        )

    return pts_per_run, dnf_mask

def _simulate_sprint_vectorised(
    pace: np.ndarray,
    driver_names: list[str],
    reliability: dict[str, float],
    runs: int,
    rng: np.random.Generator,
) -> np.ndarray:
    n = len(driver_names)
    sprint_lookup = np.array(SPRINT_PTS + [0] * max(n - len(SPRINT_PTS), 0), dtype=np.int32)

    surv = np.array([
        min(float(reliability.get(nm, 0.93)) + 0.04, 0.99) for nm in driver_names
    ])
    dnf_mask = rng.random((runs, n)) > surv[np.newaxis, :]

    pace_noise = _box_muller_normal((runs, n), rng) * (0.13 / 3.0)
    race_pace  = pace[np.newaxis, :] + pace_noise
    race_pace  = np.where(dnf_mask, -1e9, race_pace)

    order = np.argsort(-race_pace, axis=1, kind='stable')
    pts_per_run = np.zeros((runs, n), dtype=np.int32)
    for pos_i in range(min(n, len(SPRINT_PTS))):
        driver_at_pos = order[:, pos_i]
        finished = ~dnf_mask[np.arange(runs), driver_at_pos]
        pts_per_run[np.arange(runs), driver_at_pos] = np.where(
            finished, sprint_lookup[pos_i], 0
        )
    return pts_per_run

def monte_carlo(payload: dict[str, Any]) -> dict[str, Any]:
    drivers = payload.get('drivers') or []
    constructors = payload.get('constructors') or []
    runs = max(1000, min(int(payload.get('runs') or 250_000), 500_000))
    race_schedule = payload.get('raceSchedule') or []
    reliability = payload.get('reliability') or {}
    team_pace = payload.get('teamPace') or {}
    driver_skill = payload.get('driverSkill') or {}
    circuit_overtake_map = payload.get('circuitOvertake') or CIRCUIT_OVERTAKE_DEFAULT

    team_order = [canonical_team_name(c.get('name') or c.get('team_name') or c.get('team') or '') for c in constructors]
    team_order = [x for i, x in enumerate(team_order) if x and x not in team_order[:i]]

    drivers = normalize_driver_standings(drivers, team_order)
    constructors = normalize_constructors_standings(constructors, team_order)
    n = len(drivers)
    if n == 0:
        return {'error': 'No drivers', 'runs': runs}

    done = sum(1 for r in race_schedule if r.get('done'))
    total = sum(1 for r in race_schedule if not r.get('canc'))
    remaining = max(total - done, 0)
    done_sprints = sum(1 for r in race_schedule if r.get('done') and r.get('sprint'))
    total_sprints = sum(1 for r in race_schedule if (not r.get('canc')) and r.get('sprint'))
    remaining_sprints = max(total_sprints - done_sprints, 0)

    driver_names = [d.get('name', 'Unknown') for d in drivers]
    driver_teams = [d.get('team', 'Unknown') for d in drivers]
    
    rng = np.random.default_rng()
    pace_array = build_pace_model(drivers, race_schedule, team_pace, driver_skill)
    
    current_pts = np.array([float(d.get('pts', 0)) for d in drivers], dtype=np.float64)
    sim_pts = np.tile(current_pts, (runs, 1))

    # Simulate remaining races
    future_races = [r for r in race_schedule if (not r.get('done')) and (not r.get('canc'))]
    for r in future_races:
        code = r.get('n', 'MIA')
        overtake = float(circuit_overtake_map.get(code, 0.60))
        sc_chance = 0.35 # Default
        rain_chance = 0.15 # Default
        
        if r.get('sprint'):
            sprint_pts = _simulate_sprint_vectorised(pace_array, driver_names, reliability, runs, rng)
            sim_pts += sprint_pts
            
        race_pts, _ = _simulate_race_vectorised(
            pace_array, driver_names, driver_teams, reliability,
            overtake, sc_chance, rain_chance, runs, rng
        )
        sim_pts += race_pts

    # Calculate probabilities
    winner_idx = np.argmax(sim_pts, axis=1)
    win_counts = np.bincount(winner_idx, minlength=n)
    win_probs = win_counts / runs
    
    # Calculate team probabilities
    constructor_names = [
        canonical_team_name(c.get('name') or c.get('team_name') or c.get('team') or f'Team {i + 1}', TEAM_ORDER_DEFAULT)
        for i, c in enumerate(constructors)
    ]
    team_pts = np.zeros((runs, len(constructors)))
    for i, c_name in enumerate(constructor_names):
        d_indices = [j for j, d in enumerate(drivers) if d.get('team') == c_name]
        if d_indices:
            team_pts[:, i] = np.sum(sim_pts[:, d_indices], axis=1)
            
    team_winner_idx = np.argmax(team_pts, axis=1)
    team_win_counts = np.bincount(team_winner_idx, minlength=len(constructors))
    team_win_probs = team_win_counts / runs

    driver_projected_pts = np.median(sim_pts, axis=0)
    constructor_projected_pts = np.median(team_pts, axis=0) if len(constructors) else np.array([])

    driver_rows = []
    for idx, (name, prob) in enumerate(zip(driver_names, win_probs)):
        driver_rows.append({
            'name': name,
            'team': driver_teams[idx],
            'probability': round(float(prob) * 100.0, 1),
            'prob': round(float(prob) * 100.0, 1),
            'projected_pts': int(round(float(driver_projected_pts[idx]))),
            'projPts': int(round(float(driver_projected_pts[idx]))),
        })
    driver_rows.sort(key=lambda row: (-row['probability'], -row['projected_pts'], row['name']))

    constructor_probabilities = {
        name: round(float(prob) * 100.0, 1)
        for name, prob in zip(constructor_names, team_win_probs)
    }
    constructor_median_pts = {
        name: int(round(float(pts)))
        for name, pts in zip(constructor_names, constructor_projected_pts)
    }

    champ_driver = driver_rows[0] if driver_rows else {'name': 'Unknown', 'team': 'Unknown'}
    champ_constructor = max(
        constructor_probabilities,
        key=lambda name: (constructor_probabilities.get(name, 0), constructor_median_pts.get(name, 0)),
        default='Unknown',
    )

    explanations = [
        {
            'factor': 'Remaining calendar',
            'impact': 1,
            'note': f'{remaining} races and {remaining_sprints} sprints remain in the simulation.',
        },
        {
            'factor': 'Reliability',
            'impact': -1,
            'note': 'Mechanical and incident risk are applied per driver with correlated engine failures.',
        },
        {
            'factor': 'Weather variance',
            'impact': 1,
            'note': 'Wet-race multipliers and safety-car probability are included in each race run.',
        },
    ]

    return {
        'ok': True,
        'runs': runs,
        'remaining': remaining,
        'racesRemaining': remaining,
        'remainingSprints': remaining_sprints,
        'champDriver': {
            'name': champ_driver.get('name'),
            'team': champ_driver.get('team'),
        },
        'champDriverProb': champ_driver.get('probability', 0),
        'champDriverPts': champ_driver.get('projected_pts', 0),
        'champConstructor': champ_constructor,
        'champConstructorProb': constructor_probabilities.get(champ_constructor, 0),
        'champConstructorPts': constructor_median_pts.get(champ_constructor, 0),
        'podium': driver_rows[:3],
        'driverProbabilities': driver_rows,
        'constructorProbabilities': constructor_probabilities,
        'constructorMedianPts': constructor_median_pts,
        'explanations': explanations,
        'winProbabilities': {name: round(float(prob), 4) for name, prob in zip(driver_names, win_probs)},
        'teamWinProbabilities': {name: round(float(prob), 4) for name, prob in zip(constructor_names, team_win_probs)},
    }
