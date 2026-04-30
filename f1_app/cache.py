import threading
import time
from typing import Any

class SimpleCache:
    def __init__(self, max_size: int = 600, default_ttl: float = 60.0):
        self.cache: dict[str, tuple[float, Any]] = {}
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        with self._lock:
            item = self.cache.get(key)
            if item is None:
                return None
            expiry, value = item
            if time.time() < expiry:
                return value
            self.cache.pop(key, None)
            return None

    def set(self, key: str, value: Any, ttl: Any = None) -> None:
        with self._lock:
            if len(self.cache) >= self.max_size:
                oldest = min(self.cache.keys(), key=lambda k: self.cache[k][0])
                self.cache.pop(oldest, None)
            self.cache[key] = (time.time() + (self.default_ttl if ttl is None else ttl), value)

    def clear(self) -> None:
        with self._lock:
            self.cache.clear()

API_CACHE = SimpleCache()

SOURCE_HEALTH = {
    "openf1": {"ok": True, "lastOk": None, "lastError": None, "last429": None},
    "jolpica": {"ok": True, "lastOk": None, "lastError": None, "last429": None},
    "weather": {"ok": True, "lastOk": None, "lastError": None, "last429": None},
}

def mark_source_ok(source: str) -> None:
    info = SOURCE_HEALTH.setdefault(source, {})
    info["ok"] = True
    info["lastOk"] = time.time()

def mark_source_error(source: str, err: object, is_429: bool = False) -> None:
    info = SOURCE_HEALTH.setdefault(source, {})
    info["ok"] = False
    info["lastError"] = str(err)
    if is_429:
        info["last429"] = time.time()
