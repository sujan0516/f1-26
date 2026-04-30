## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="your_key_here"
python app.py
```

Open http://127.0.0.1:8000

## Live Timing Data Intervals

The app uses separate refresh layers to avoid OpenF1 HTTP 429 rate-limit errors:

| Layer | Interval | Endpoints |
|---|---|---|
| Speed telemetry | 1 second | `/car_data` |
| Location telemetry | 2 seconds | `/location` |
| Heavy live timing | 5–10 seconds | positions, intervals, stints, laps, radio, race control |
| Weather | 5–10 minutes | open-meteo |
| Standings | 60 seconds | Jolpica / OpenF1 championships |

## Environment Variables

```bash
# Refresh intervals
export F1_SPEED_REFRESH_SECONDS=1
export F1_LOCATION_REFRESH_SECONDS=2
export F1_HEAVY_LIVE_REFRESH_SECONDS=5

# Cache TTLs (must match or exceed refresh intervals)
export F1_SPEED_FETCH_TTL=1
export F1_LOCATION_FETCH_TTL=2
export F1_HEAVY_FETCH_TTL=5
export F1_WEATHER_FETCH_TTL=600
export F1_STANDINGS_FETCH_TTL=60

# Feature toggles
export F1_ENABLE_SPEED_STREAM=1
export F1_ENABLE_LOCATION_STREAM=1
```

If OpenF1 is returning 429 errors, increase the heavy interval:

```bash
export F1_HEAVY_LIVE_REFRESH_SECONDS=10
export F1_HEAVY_FETCH_TTL=10
```

## Radio transcription

The live timing radio panel now includes a `Transcript` button.

- The browser sends the selected OpenF1 radio clip URL to the Python backend.
- The Python backend downloads the audio clip.
- The backend sends the clip to OpenAI's audio transcription API.
- The transcript is cached in memory by audio URL for faster repeat loads.

Optional environment variables:

- `OPENAI_API_KEY` required for transcription
- `OPENAI_TRANSCRIBE_MODEL` optional, defaults to `gpt-4o-mini-transcribe`

If no API key is configured, the UI will show a backend configuration error instead of silently failing.


## Local radio transcription

This build does not require an OpenAI API key for radio transcripts. It uses a local `faster-whisper` model on your machine.

Notes:
- The first transcript request downloads the Whisper model once.
- Default model: `base.en`
- You can change it with `LOCAL_TRANSCRIBE_MODEL`, for example `small.en` for better accuracy or `tiny.en` for faster CPU performance.

Example:

```bash
export LOCAL_TRANSCRIBE_MODEL=small.en
python app.py
```
