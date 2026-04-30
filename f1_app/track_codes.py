from typing import Optional

TRACK_ALIASES = {
    "AUS": ["australia", "melbourne", "albert park"],
    "CHN": ["china", "shanghai"],
    "JPN": ["japan", "suzuka"],
    "MIA": ["miami"],
    "CAN": ["canada", "montreal", "gilles villeneuve", "villeneuve"],
    "MON": ["monaco", "monte carlo"],
    "BCN": ["spain", "barcelona", "catalunya", "esp"],
    "AUT": ["austria", "spielberg", "red bull ring"],
    "GBR": ["britain", "great britain", "silverstone", "uk"],
    "BEL": ["belgium", "spa", "spa-francorchamps"],
    "HUN": ["hungary", "hungaroring", "budapest"],
    "NED": ["netherlands", "dutch", "zandvoort"],
    "ITA": ["italy", "monza"],
    "MAD": ["madrid"],
    "AZE": ["azerbaijan", "baku"],
    "SGP": ["singapore", "marina bay", "sin"],
    "USA": ["united states", "austin", "cota", "americas"],
    "MEX": ["mexico", "mexico city", "rodriguez"],
    "BRA": ["brazil", "sao paulo", "interlagos"],
    "LVS": ["las vegas", "vegas", "lvg"],
    "QAT": ["qatar", "lusail", "losail"],
    "ABU": ["abu dhabi", "yas marina"],
}

def normalize_track_code(value: Optional[str]) -> str:
    s = str(value or "").strip().lower()
    if not s:
        return "MIA"

    upper = s.upper()
    if upper in TRACK_ALIASES:
        return upper

    for code, aliases in TRACK_ALIASES.items():
        if any(alias in s for alias in aliases):
            return code

    return upper

def get_track_code_from_session(sess: dict) -> str:
    text = " ".join(str(sess.get(k) or "") for k in [
        "meeting_name",
        "meeting_official_name",
        "location",
        "country_name",
        "circuit_short_name",
    ])
    return normalize_track_code(text)
