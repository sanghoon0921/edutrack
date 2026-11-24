from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any, TypeVar

from django.core.cache.backends.redis import RedisCache


logger = logging.getLogger("edutrack.cache")
T = TypeVar("T")


class ResilientRedisCache(RedisCache):
    """
    Redis가 잠시 끊겨도 원본 DB 조회로 계속 동작하도록 하는 보조 백엔드입니다.

    캐시는 정답 데이터 저장소가 아니라 외부 DB 조회를 줄이는 가속 계층입니다.
    연결 실패 후 짧은 시간 동안 회로를 열어 매 요청마다 Redis 재연결을 반복하지
    않으며, 시간이 지나면 자동으로 한 번 재시도합니다.
    """

    def __init__(self, server: str, params: dict[str, Any]) -> None:
        super().__init__(server, params)
        try:
            self._cooldown_seconds = max(
                1.0,
                float(os.environ.get("CACHE_FAILURE_COOLDOWN_SECONDS", "30")),
            )
        except (TypeError, ValueError):
            self._cooldown_seconds = 30.0
        self._state_lock = threading.Lock()
        self._unavailable_until = 0.0
        self._last_warning_at = 0.0

    def _circuit_is_open(self) -> bool:
        with self._state_lock:
            return time.monotonic() < self._unavailable_until

    def _mark_success(self) -> None:
        with self._state_lock:
            self._unavailable_until = 0.0

    def _mark_failure(self, operation: str, error: Exception) -> None:
        now = time.monotonic()
        should_log = False
        with self._state_lock:
            self._unavailable_until = max(
                self._unavailable_until,
                now + self._cooldown_seconds,
            )
            if now - self._last_warning_at >= 60:
                self._last_warning_at = now
                should_log = True
        if should_log:
            logger.warning(
                "redis_cache_unavailable operation=%s error_type=%s",
                operation,
                type(error).__name__,
            )

    def _safe(self, operation: str, default: T, callback: Callable[[], T]) -> T:
        if self._circuit_is_open():
            return default
        try:
            result = callback()
        except Exception as error:
            self._mark_failure(operation, error)
            return default
        self._mark_success()
        return result

    def add(self, key: str, value: Any, timeout=None, version=None) -> bool:
        return self._safe(
            "add",
            False,
            lambda: super(ResilientRedisCache, self).add(key, value, timeout, version),
        )

    def get(self, key: str, default=None, version=None) -> Any:
        return self._safe(
            "get",
            default,
            lambda: super(ResilientRedisCache, self).get(key, default, version),
        )

    def set(self, key: str, value: Any, timeout=None, version=None) -> bool:
        return self._safe(
            "set",
            False,
            lambda: super(ResilientRedisCache, self).set(key, value, timeout, version),
        )

    def touch(self, key: str, timeout=None, version=None) -> bool:
        return self._safe(
            "touch",
            False,
            lambda: super(ResilientRedisCache, self).touch(key, timeout, version),
        )

    def delete(self, key: str, version=None) -> bool:
        return self._safe(
            "delete",
            False,
            lambda: super(ResilientRedisCache, self).delete(key, version),
        )

    def get_many(self, keys: Iterable[str], version=None) -> dict[str, Any]:
        key_list = list(keys)
        return self._safe(
            "get_many",
            {},
            lambda: super(ResilientRedisCache, self).get_many(key_list, version),
        )

    def set_many(
        self,
        data: Mapping[str, Any],
        timeout=None,
        version=None,
    ) -> list[str]:
        payload = dict(data)
        return self._safe(
            "set_many",
            list(payload),
            lambda: super(ResilientRedisCache, self).set_many(
                payload,
                timeout,
                version,
            ),
        )

    def delete_many(self, keys: Iterable[str], version=None) -> int:
        key_list = list(keys)
        return self._safe(
            "delete_many",
            0,
            lambda: super(ResilientRedisCache, self).delete_many(key_list, version),
        )

    def clear(self) -> bool:
        return self._safe(
            "clear",
            False,
            lambda: super(ResilientRedisCache, self).clear(),
        )
