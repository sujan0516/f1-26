import json
import logging
import ssl
import urllib.error
import urllib.request
import time
from typing import Any, Optional
from .cache import API_CACHE, mark_source_error, mark_source_ok
from .config import (
    OPENF1_SPEED_FETCH_TTL,
    OPENF1_LOCATION_FETCH_TTL,
    OPENF1_HEAVY_FETCH_TTL,
    WEATHER_FETCH_TTL,
    STANDINGS_FETCH_TTL,
)

logger = logging.getLogger("f1_app")

def source_for_url(url: str) -> str:
    if "openf1" in url:
        return "openf1"
    if "jolpi" in url or "ergast" in url:
        return "jolpica"
    if "meteo" in url or "weather" in url:
        return "weather"
    return "unknown"

def build_ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

SSL_CTX = build_ssl_context()

def ttl_for_url(url: str) -> float:
    if "/drivers" in url or "standings" in url:
        return STANDINGS_FETCH_TTL
    if "meteo" in url or "weather" in url:
        return WEATHER_FETCH_TTL
    if "/car_data" in url:
        return OPENF1_SPEED_FETCH_TTL
    if "/location" in url:
        return OPENF1_LOCATION_FETCH_TTL
    return OPENF1_HEAVY_FETCH_TTL

import threading

_URL_LOCKS = {}
_URL_LOCKS_LOCK = threading.Lock()

def _get_url_lock(url: str) -> threading.Lock:
    with _URL_LOCKS_LOCK:
        if url not in _URL_LOCKS:
            _URL_LOCKS[url] = threading.Lock()
        return _URL_LOCKS[url]

def http_json(url: str, timeout: float = 8.0, use_cache: bool = True, ttl: Optional[float] = None) -> Any:
    source = source_for_url(url)
    
    # Fast path: check cache without lock first
    if API_CACHE.get(f"BLOCK:{source}"):
        cached = API_CACHE.get(url)
        if cached is not None:
            return cached
        return None
    if use_cache:
        cached = API_CACHE.get(url)
        if cached is not None:
            return cached

    lock = _get_url_lock(url) if use_cache else None
    
    if lock:
        lock.acquire()
        try:
            # Double check inside lock
            if API_CACHE.get(f"BLOCK:{source}"):
                cached = API_CACHE.get(url)
                if cached is not None:
                    return cached
                return None
            cached = API_CACHE.get(url)
            if cached is not None:
                return cached
                
            return _do_fetch(url, timeout, use_cache, ttl, source)
        finally:
            lock.release()
    else:
        return _do_fetch(url, timeout, use_cache, ttl, source)

def _do_fetch(url: str, timeout: float, use_cache: bool, ttl: Optional[float], source: str) -> Any:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        mark_source_ok(source)
        if use_cache:
            API_CACHE.set(url, data, ttl=ttl if ttl is not None else ttl_for_url(url))
        return data
    except urllib.error.HTTPError as e:
        if e.code == 429:
            mark_source_error(source, e, is_429=True)
            API_CACHE.set(f"BLOCK:{source}", True, ttl=30.0)
            cached = API_CACHE.get(url)
            if cached is not None:
                logger.warning("429 for %s. Serving cached response.", source)
                return cached
            logger.warning("429 for %s. No cache available.", source)
            return None
        if e.code == 404:
            return None
        mark_source_error(source, e)
        logger.error("HTTP error %s fetching %s", e.code, url)
        return None
    except Exception as e:
        mark_source_error(source, e)
        cached = API_CACHE.get(url)
        if cached is not None:
            logger.warning("Fetch failed. Serving cached response for %s", url)
            return cached
        logger.error("Fetch failed for %s: %s", url, e)
        return None

def safe_http_json(url: str, timeout: float = 8.0, use_cache: bool = True, ttl: Optional[float] = None) -> Any:
    try:
        return http_json(url, timeout=timeout, use_cache=use_cache, ttl=ttl)
    except Exception:
        return None
