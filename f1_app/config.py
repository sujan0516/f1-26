from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR = BASE_DIR / "data"

CURRENT_F1_YEAR = int(os.getenv("CURRENT_F1_YEAR", "2026"))

OPENF1 = "https://api.openf1.org/v1"
JOLPICA = "https://api.jolpi.ca/ergast/f1"

SPEED_REFRESH_SECONDS = float(os.getenv("F1_SPEED_REFRESH_SECONDS", "1.0"))
LOCATION_REFRESH_SECONDS = float(os.getenv("F1_LOCATION_REFRESH_SECONDS", "2.0"))
HEAVY_LIVE_REFRESH_SECONDS = float(os.getenv("F1_HEAVY_LIVE_REFRESH_SECONDS", "5.0"))

OPENF1_SPEED_FETCH_TTL = float(os.getenv("F1_SPEED_FETCH_TTL", "1.0"))
OPENF1_LOCATION_FETCH_TTL = float(os.getenv("F1_LOCATION_FETCH_TTL", "2.0"))
OPENF1_HEAVY_FETCH_TTL = float(os.getenv("F1_HEAVY_FETCH_TTL", "5.0"))
WEATHER_FETCH_TTL = float(os.getenv("F1_WEATHER_FETCH_TTL", "600.0"))
STANDINGS_FETCH_TTL = float(os.getenv("F1_STANDINGS_FETCH_TTL", "60.0"))

PIT_LANE_LOSS = 22.0

TYRE_DEG_RATE = {
    "SOFT": 0.045,
    "MEDIUM": 0.025,
    "HARD": 0.015,
    "INTERMEDIATE": 0.060,
    "WET": 0.050,
}

TYRE_BASE_LIFE = {
    "SOFT": 18,
    "MEDIUM": 30,
    "HARD": 45,
    "INTERMEDIATE": 26,
    "WET": 32,
}

TRACK_WEAR_MULTIPLIER = {
    "Low": 0.85,
    "Medium": 1.00,
    "High": 1.18,
    "Extreme": 1.35,
}

DEFAULT_PIT_LOSS_BY_TRACK = {
    "AUS": 22.0,
    "CHN": 22.5,
    "JPN": 22.0,
    "MIA": 21.8,
    "CAN": 20.5,
    "MON": 28.0,
    "BCN": 23.0,
    "AUT": 20.0,
    "GBR": 21.0,
    "BEL": 23.5,
    "HUN": 22.5,
    "NED": 21.5,
    "ITA": 24.5,
    "MAD": 22.5,
    "AZE": 22.0,
    "SGP": 27.0,
    "USA": 22.0,
    "MEX": 22.5,
    "BRA": 21.0,
    "LVS": 24.0,
    "QAT": 24.0,
    "ABU": 22.0,
}

TRACK_CODES = [
    "AUS", "CHN", "JPN", "MIA", "CAN", "MON", "BCN", "AUT",
    "GBR", "BEL", "HUN", "NED", "ITA", "MAD", "AZE", "SGP",
    "USA", "MEX", "BRA", "LVS", "QAT", "ABU"
]
TEAM_ORDER_DEFAULT = [
    'Mercedes', 'Ferrari', 'McLaren', 'Red Bull', 'Racing Bulls',
    'Haas', 'Alpine', 'Williams', 'Aston Martin', 'Audi', 'Cadillac'
]

DRIVER_HEADSHOT_OVERRIDES = {
    "Lando Norris": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/mclaren/lannor01/2026mclarenlannor01right.webp",
    "Max Verstappen": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/redbullracing/maxver01/2026redbullracingmaxver01right.webp",
    "Gabriel Bortoleto": "https://media.formula1.com/image/upload/c_fill,w_720/q_auto/v1740000001/common/f1/2026/audi/gabbor01/2026audigabbor01right.webp",
    "Isack Hadjar": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/redbullracing/isahad01/2026redbullracingisahad01right.webp",
    "Pierre Gasly": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/alpine/piegas01/2026alpinepiegas01right.webp",
    "Sergio Perez": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/cadillac/serper01/2026cadillacserper01right.webp",
    "Kimi Antonelli": "https://media.formula1.com/image/upload/c_lfill,w_720/q_auto/v1740000001/common/f1/2026/mercedes/andant01/2026mercedesandant01right.webp",
    "Andrea Kimi Antonelli": "https://media.formula1.com/image/upload/c_lfill,w_720/q_auto/v1740000001/common/f1/2026/mercedes/andant01/2026mercedesandant01right.webp",
    "Fernando Alonso": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/astonmartin/feralo01/2026astonmartinferalo01right.webp",
    "Charles Leclerc": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/ferrari/chalec01/2026ferrarichalec01right.webp",
    "Lance Stroll": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/astonmartin/lanstr01/2026astonmartinlanstr01right.webp",
    "Alexander Albon": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/williams/alealb01/2026williamsalealb01right.webp",
    "Nico Hulkenberg": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/audi/nichul01/2026audinichul01right.webp",
    "Liam Lawson": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/racingbulls/lialaw01/2026racingbullslialaw01right.webp",
    "Esteban Ocon": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/haas/estoco01/2026haasestoco01right.webp",
    "Arvid Lindblad": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/racingbulls/arvlin01/2026racingbullsarvlin01right.webp",
    "Franco Colapinto": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/alpine/fracol01/2026alpinefracol01right.webp",
    "Lewis Hamilton": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/ferrari/lewham01/2026ferrarilewham01right.webp",
    "Carlos Sainz": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/williams/carsai01/2026williamscarsai01right.webp",
    "George Russell": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/mercedes/georus01/2026mercedesgeorus01right.webp",
    "Valtteri Bottas": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/cadillac/valbot01/2026cadillacvalbot01right.webp",
    "Oscar Piastri": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/mclaren/oscpia01/2026mclarenoscpia01right.webp",
    "Oliver Bearman": "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026/haas/olibea01/2026haasolibea01right.webp",
}

TEAM_LOGOS = {
    'Mercedes': 'https://media.formula1.com/content/dam/fom-website/teams/2024/mercedes-logo.png',
    'Ferrari': 'https://media.formula1.com/content/dam/fom-website/teams/2024/ferrari-logo.png',
    'McLaren': 'https://media.formula1.com/content/dam/fom-website/teams/2024/mclaren-logo.png',
    'Red Bull': 'https://media.formula1.com/content/dam/fom-website/teams/2024/red-bull-racing-logo.png',
    'Racing Bulls': 'https://media.formula1.com/content/dam/fom-website/teams/2024/rb-logo.png',
    'Alpine': 'https://media.formula1.com/content/dam/fom-website/teams/2024/alpine-logo.png',
    'Williams': 'https://media.formula1.com/content/dam/fom-website/teams/2024/williams-logo.png',
    'Aston Martin': 'https://media.formula1.com/content/dam/fom-website/teams/2024/aston-martin-logo.png',
    'Haas': 'https://media.formula1.com/content/dam/fom-website/teams/2024/haas-f1-team-logo.png',
    'Audi': 'https://cdn.simpleicons.org/audi/white',
    'Cadillac': 'https://cdn.simpleicons.org/cadillac/white',
}

TEAM_COLORS = {
    'Mercedes': '#00d2be', 'Ferrari': '#e8002d', 'McLaren': '#ff8000', 'Red Bull': '#3671c6',
    'Racing Bulls': '#6692ff', 'Alpine': '#0090ff', 'Williams': '#37bedd', 'Aston Martin': '#006f62',
    'Haas': '#b6babd', 'Audi': '#c0c0c0', 'Cadillac': '#b50000'
}

