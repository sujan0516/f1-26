from pathlib import Path

TRACK_CODES = [
    "AUS", "CHN", "JPN", "MIA", "CAN", "MON", "BCN", "AUT",
    "GBR", "BEL", "HUN", "NED", "ITA", "MAD", "AZE", "SGP",
    "USA", "MEX", "BRA", "LVS", "QAT", "ABU"
]

folder = Path("static/tracks")

missing = [
    code for code in TRACK_CODES
    if not (folder / f"{code}.svg").exists()
]

if missing:
    print(f"FAILED: Missing track SVG files: {', '.join(missing)}")
    exit(1)

print("PASSED: All track SVG files exist")
