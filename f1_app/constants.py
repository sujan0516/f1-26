DRIVER_ID_MAP = {
    'russell': 'George Russell',
    'antonelli': 'Kimi Antonelli',
    'leclerc': 'Charles Leclerc',
    'hamilton': 'Lewis Hamilton',
    'bearman': 'Oliver Bearman',
    'norris': 'Lando Norris',
    'gasly': 'Pierre Gasly',
    'max_verstappen': 'Max Verstappen',
    'lawson': 'Liam Lawson',
    'arvid_lindblad': 'Arvid Lindblad',
    'hadjar': 'Isack Hadjar',
    'piastri': 'Oscar Piastri',
    'sainz': 'Carlos Sainz',
    'bortoleto': 'Gabriel Bortoleto',
    'colapinto': 'Franco Colapinto',
    'tsunoda': 'Yuki Tsunoda',
    'ocon': 'Esteban Ocon',
    'hulkenberg': 'Nico Hülkenberg',
    'albon': 'Alexander Albon',
    'bottas': 'Valtteri Bottas',
    'perez': 'Sergio Pérez',
    'alonso': 'Fernando Alonso',
    'stroll': 'Lance Stroll',
}

DRIVER_TEAM_MAP = {
    "russell": "Mercedes", "antonelli": "Mercedes",
    "leclerc": "Ferrari", "hamilton": "Ferrari",
    "norris": "McLaren", "piastri": "McLaren",
    "verstappen": "Red Bull", "hadjar": "Red Bull",
    "lawson": "Racing Bulls", "lindblad": "Racing Bulls",
    "bearman": "Haas", "ocon": "Haas",
    "gasly": "Alpine", "colapinto": "Alpine",
    "sainz": "Williams", "albon": "Williams",
    "alonso": "Aston Martin", "stroll": "Aston Martin",
    "hulkenberg": "Audi", "bortoleto": "Audi",
    "bottas": "Cadillac", "perez": "Cadillac",
}

CIRCUIT_ID_MAP = {
    'albert_park': 'AUS', 'shanghai': 'CHN', 'suzuka': 'JPN',
    'bahrain': 'BAH', 'jeddah': 'SAU', 'miami': 'MIA',
    'villeneuve': 'CAN', 'monaco': 'MON', 'catalunya': 'BCN',
    'red_bull_ring': 'AUT', 'silverstone': 'GBR', 'spa': 'BEL',
    'hungaroring': 'HUN', 'zandvoort': 'NED', 'monza': 'ITA',
    'madrid': 'MAD', 'baku': 'AZE', 'marina_bay': 'SGP',
    'americas': 'USA', 'rodriguez': 'MEX', 'interlagos': 'BRA',
    'las_vegas': 'LVS', 'losail': 'QAT', 'yas_marina': 'ABU',
}

TYRE_COLORS_DEFAULT = {'SOFT': '#e8002d', 'MEDIUM': '#f5c842', 'HARD': '#e8eaf2', 'INTERMEDIATE': '#00d47e', 'WET': '#5aafff'}
TYRE_PACE_DEFAULT = {'SOFT': 1.03, 'MEDIUM': 1.0, 'HARD': 0.985, 'INTERMEDIATE': 0.96, 'WET': 0.94}
CIRCUIT_OVERTAKE_DEFAULT = {
    'AUS': 0.70, 'CHN': 0.65, 'JPN': 0.55, 'MIA': 0.65, 'CAN': 0.80, 'MON': 0.20, 'BCN': 0.55,
    'AUT': 0.75, 'GBR': 0.60, 'BEL': 0.70, 'HUN': 0.30, 'NED': 0.55, 'ITA': 0.75, 'MAD': 0.65,
    'AZE': 0.80, 'SGP': 0.35, 'USA': 0.65, 'MEX': 0.70, 'BRA': 0.70, 'LVS': 0.75, 'QAT': 0.60, 'ABU': 0.65
}

PTS_TABLE = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
SPRINT_PTS = [8, 7, 6, 5, 4, 3, 2, 1]
