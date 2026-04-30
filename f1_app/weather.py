import time
import urllib.parse
from datetime import datetime
from typing import Any, Optional, Dict, Tuple
from .http_client import safe_http_json

TRACK_COORDS_DEFAULT = {
    'AUS': {'lat': -37.8497, 'lon': 144.968},
    'CHN': {'lat': 31.3389, 'lon': 121.22},
    'JPN': {'lat': 34.8431, 'lon': 136.541},
    'MIA': {'lat': 25.9581, 'lon': -80.2389},
    'CAN': {'lat': 45.5005, 'lon': -73.5228},
    'MON': {'lat': 43.7347, 'lon': 7.4206},
    'BCN': {'lat': 41.57, 'lon': 2.2611},
    'AUT': {'lat': 47.2197, 'lon': 14.7647},
    'GBR': {'lat': 52.0786, 'lon': -1.0169},
    'BEL': {'lat': 50.4372, 'lon': 5.9714},
    'HUN': {'lat': 47.5817, 'lon': 19.2508},
    'NED': {'lat': 52.3888, 'lon': 4.5409},
    'ITA': {'lat': 45.6156, 'lon': 9.2811},
    'MAD': {'lat': 40.4168, 'lon': -3.7038},
    'AZE': {'lat': 40.3725, 'lon': 49.8533},
    'SGP': {'lat': 1.2914, 'lon': 103.864},
    'USA': {'lat': 30.1328, 'lon': -97.6411},
    'MEX': {'lat': 19.4042, 'lon': -99.0907},
    'BRA': {'lat': -23.7036, 'lon': -46.6997},
    'LVS': {'lat': 36.1147, 'lon': -115.173},
    'QAT': {'lat': 25.49, 'lon': 51.4542},
    'ABU': {'lat': 24.4672, 'lon': 54.6031},
}

def wmo_to_condition(code: int) -> Tuple[str, str]:
    if code == 0: return 'Clear', '☀️'
    if code in {1, 2, 3}: return 'Partly Cloudy', '⛅'
    if code in {45, 48}: return 'Fog', '🌫️'
    if code in {51, 53, 55, 61, 63, 65}: return 'Rain', '🌧️'
    if code in {71, 73, 75}: return 'Snow', '❄️'
    if code >= 95: return 'Thunderstorm', '⛈️'
    return 'Cloudy', '☁️'

def build_weather_backend(track_code: Optional[str]) -> Dict[str, Any]:
    code = str(track_code or 'MIA').upper()
    coords = TRACK_COORDS_DEFAULT.get(code)
    if not coords:
        return {'ok': False, 'error': 'Unknown track coordinates'}
    
    query = urllib.parse.urlencode({
        'latitude': coords.get('lat'),
        'longitude': coords.get('lon'),
        'daily': 'precipitation_probability_max,temperature_2m_max,wind_speed_10m_max,weather_code',
        'timezone': 'auto',
        'forecast_days': 7,
    })
    
    fallback = fallback_weather(code)
    data = safe_http_json(f'https://api.open-meteo.com/v1/forecast?{query}', timeout=6.0) or {}
    daily = data.get('daily') or {}
    times = daily.get('time') or []
    if not times:
        return fallback

    # Find the sunday (race day)
    race_idx = 0
    for i, day_str in enumerate(times):
        try:
            if datetime.fromisoformat(day_str).weekday() == 6:
                race_idx = i; break
        except Exception: pass

    rain_series = daily.get('precipitation_probability_max') or []
    temp_series = daily.get('temperature_2m_max') or []
    wind_series = daily.get('wind_speed_10m_max') or []
    weather_codes = daily.get('weather_code') or []
    rain = rain_series[race_idx] if race_idx < len(rain_series) else 0
    temp = temp_series[race_idx] if race_idx < len(temp_series) else 25
    wind = wind_series[race_idx] if race_idx < len(wind_series) else 10
    weather_code = weather_codes[race_idx] if race_idx < len(weather_codes) else 0
    condition, icon = wmo_to_condition(weather_code)
    
    return {
        'ok': True,
        'trackCode': code,
        'generatedAt': time.time(),
        'dataSourceLabel': 'LIVE WEATHER',
        'weather': {
            'rainChance': float(rain or 0) / 100.0,
            'temp': round(float(temp or 25)),
            'windSpeed': round(float(wind or 10)),
            'condition': condition,
            'icon': icon,
            'trendTemp': [round(float(x or 0)) for x in temp_series[:7]],
            'trendWind': [round(float(x or 0)) for x in wind_series[:7]],
            'source': 'live',
        }
    }


def fallback_weather(code: str) -> Dict[str, Any]:
    defaults = {
        'MIA': (0.35, 31, 18, 'Hot / Storm Risk', '🌦'),
        'SGP': (0.45, 30, 12, 'Humid / Showers', '🌦'),
        'GBR': (0.35, 18, 24, 'Cool / Changeable', '🌥'),
        'BEL': (0.40, 17, 18, 'Mixed', '🌦'),
        'QAT': (0.05, 34, 16, 'Hot / Dry', '☀️'),
        'ABU': (0.02, 30, 14, 'Clear', '☀️'),
    }
    rain, temp, wind, condition, icon = defaults.get(code, (0.20, 25, 14, 'Forecast Estimate', '🌤'))
    return {
        'ok': True,
        'trackCode': code,
        'generatedAt': time.time(),
        'weather': {
            'rainChance': rain,
            'temp': temp,
            'windSpeed': wind,
            'condition': condition,
            'icon': icon,
            'trendTemp': [temp - 2, temp - 1, temp, temp + 1, temp, temp - 1, temp],
            'trendWind': [max(0, wind - 4), wind - 2, wind, wind + 3, wind + 1, wind, max(0, wind - 1)],
            'source': 'fallback',
        },
        'dataSourceLabel': 'FALLBACK WEATHER',
    }
