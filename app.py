import json
import os
import logging
from flask import render_template
from f1_app import create_app
from f1_app.config import DATA_DIR

app = create_app()

# Load Bootstrap Data
BOOTSTRAP_DATA = json.loads((DATA_DIR / 'bootstrap_data.json').read_text())

def audit_bootstrap_driver_stats(data: dict) -> None:
    logger = logging.getLogger('f1_app')
    driver_db = data.get('DRIVER_DB') or {}
    for name, stats in driver_db.items():
        if not isinstance(stats, dict): continue
        expected = ['starts', 'wins', 'podiums']
        missing = [k for k in expected if k not in stats]
        if missing:
            logger.warning(f"Audit: Driver {name} missing keys {missing}")

audit_bootstrap_driver_stats(BOOTSTRAP_DATA)

@app.get("/")
def index():
    return render_template(
        "indexsp_python_backend.html",
        bootstrap_json=json.dumps(BOOTSTRAP_DATA)
    )

@app.get("/indexsp_python_backend.html")
def index_template_alias():
    return index()

if __name__ == '__main__':
    # Background threads for heartbeat etc can be added here
    # The factory create_app handles blueprint registration and logging config
    app.run(host='127.0.0.1', port=8000, debug=True, use_reloader=True)
