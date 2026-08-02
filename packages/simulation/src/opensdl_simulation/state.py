from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any


class SimulationState:
    """Thread-safe state container shared by related virtual capabilities."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._lock = RLock()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return deepcopy(self._data.get(key, default))

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = deepcopy(value)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._data)

    def restore(self, snapshot: dict[str, Any]) -> None:
        with self._lock:
            self._data = deepcopy(snapshot)
