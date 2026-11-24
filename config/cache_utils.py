from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable, Mapping
from threading import Lock
from time import monotonic
from typing import Any

from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger("edutrack.cache")

_LOG_INTERVAL_SECONDS = 60.0
_last_error_at = 0.0
_failure_until = 0.0
_state_lock = Lock()


def build_cache_key(*parts: object) -> str:
    """캐시 백엔드 종류와 관계없이 안전한 짧은 키를 만듭니다."""

    cleaned_parts: list[str] = []
    for part in parts:
        value = str(part).strip().replace(" ", "-")
        value = "".join(character for character in value if character.isprintable())
        cleaned_parts.append(value or "-")

    key = "edutrack:" + ":".join(cleaned_parts)
    if len(key) <= 220:
        return key

    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"edutrack:hashed:{digest}"


def _cooldown_seconds() -> float:
    try:
        return max(
            1.0,
            float(getattr(settings, "CACHE_FAILURE_COOLDOWN_SECONDS", 30)),
        )
    except (TypeError, ValueError):
        return 30.0


def _circuit_is_open() -> bool:
    with _state_lock:
        return monotonic() < _failure_until


def _mark_success() -> None:
    global _failure_until
    with _state_lock:
        _failure_until = 0.0


def _mark_failure(operation: str, exc: Exception) -> None:
    """캐시 장애 시 짧게 우회하고 로그 폭주를 막습니다."""

    global _last_error_at, _failure_until
    now = monotonic()
    should_log = False

    with _state_lock:
        _failure_until = max(_failure_until, now + _cooldown_seconds())
        if now - _last_error_at >= _LOG_INTERVAL_SECONDS:
            _last_error_at = now
            should_log = True

    if should_log:
        logger.warning(
            "cache_unavailable operation=%s error_type=%s",
            operation,
            exc.__class__.__name__,
        )


def safe_cache_get(key: str, default: Any = None) -> Any:
    if _circuit_is_open():
        return default
    try:
        value = cache.get(key, default)
    except Exception as exc:  # 캐시는 가속 장치이므로 장애가 페이지 장애가 되면 안 됩니다.
        _mark_failure("get", exc)
        return default
    _mark_success()
    return value


def safe_cache_set(key: str, value: Any, timeout: int | None = None) -> bool:
    if _circuit_is_open():
        return False
    try:
        result = cache.set(key, value, timeout=timeout)
    except Exception as exc:
        _mark_failure("set", exc)
        return False
    _mark_success()
    return bool(result is not False)


def safe_cache_delete(key: str) -> bool:
    if _circuit_is_open():
        return False
    try:
        result = cache.delete(key)
    except Exception as exc:
        _mark_failure("delete", exc)
        return False
    _mark_success()
    return bool(result)


def safe_cache_get_many(keys: Iterable[str]) -> dict[str, Any]:
    key_list = list(keys)
    if not key_list or _circuit_is_open():
        return {}
    try:
        values = cache.get_many(key_list)
    except Exception as exc:
        _mark_failure("get_many", exc)
        return {}
    _mark_success()
    return values


def safe_cache_set_many(
    values: Mapping[str, Any],
    timeout: int | None = None,
) -> bool:
    data = dict(values)
    if not data:
        return True
    if _circuit_is_open():
        return False
    try:
        failed_keys = cache.set_many(data, timeout=timeout)
    except Exception as exc:
        _mark_failure("set_many", exc)
        return False
    _mark_success()
    return not failed_keys


def safe_cache_delete_many(keys: Iterable[str]) -> bool:
    key_list = list(keys)
    if not key_list:
        return True
    if _circuit_is_open():
        return False
    try:
        cache.delete_many(key_list)
    except Exception as exc:
        _mark_failure("delete_many", exc)
        return False
    _mark_success()
    return True


def cache_roundtrip_is_healthy() -> bool:
    """준비 상태 점검에서 캐시를 짧게 왕복 확인합니다."""

    if _circuit_is_open():
        return False

    key = build_cache_key("health", "cache")
    marker = f"ok:{monotonic()}"
    try:
        stored = cache.set(key, marker, timeout=5)
        healthy = stored is not False and cache.get(key) == marker
        cache.delete(key)
    except Exception as exc:
        _mark_failure("healthcheck", exc)
        return False

    if healthy:
        _mark_success()
    return bool(healthy)


def reset_cache_circuit_for_tests() -> None:
    """테스트 격리를 위한 내부 상태 초기화 함수입니다."""

    global _last_error_at, _failure_until
    with _state_lock:
        _last_error_at = 0.0
        _failure_until = 0.0
