import requests
import time

BASE = "http://127.0.0.1:8000"

REQUIRED_JSON_ROUTES = [
    "/api/routes",
    "/api/source-health",
    "/api/feature-health",
    "/api/tyre-strategy",
    "/api/pit-predictor",
    "/api/race-strategy-timeline",
    "/api/track-shape",
    "/api/practice-live-timing",
    "/api/live-location",
    "/api/weather",
]

if __name__ == "__main__":
    print("Smoke-testing routes (ensure `python app.py` is running)...\n")
    passed = 0
    failed = 0
    try:
        for path in REQUIRED_JSON_ROUTES:
            try:
                r = requests.get(BASE + path, timeout=15)
                ct = r.headers.get("content-type", "")
                if r.status_code == 200 and "application/json" in ct:
                    print(f"  ✓ {path}")
                    passed += 1
                else:
                    print(f"  ✗ {path}  → HTTP {r.status_code}  content-type: {ct!r}")
                    failed += 1
            except Exception as e:
                print(f"  ✗ {path}  → ERROR: {e}")
                failed += 1
    except Exception as e:
        print(f"Could not connect to server: {e}")
        raise SystemExit(1)

    print(f"\n{passed} passed / {failed} failed")
    if failed:
        raise SystemExit(1)
    print("All route tests passed ✓")
