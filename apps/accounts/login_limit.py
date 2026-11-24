"""로그인 시도 제한(11/24 전체 점검): 같은 아이디를 같은 곳(IP)에서 5번 틀리면 15분 동안 잠급니다.

맞게 로그인하면 다시 0부터 셉니다. 아이디만으로 잠그면 다른 사람이 일부러 남의 아이디를 잠글 수 있어서 IP와 함께 봅니다.
기록은 캐시(사무실 서버는 프로그램 메모리)에만 두므로 서버를 다시 켜면 풀립니다.
"""
from __future__ import annotations

import hashlib
import time

from config.cache_utils import safe_cache_delete, safe_cache_get, safe_cache_set

LIMIT = 5
LOCK_SECONDS = 15 * 60
LOCK_MESSAGE = '비밀번호를 5번 잘못 입력해 이 아이디를 15분 동안 잠갔습니다. 잠시 후 다시 시도해 주세요.'


def client_ip(request) -> str:
    return (getattr(request, 'META', {}) or {}).get('REMOTE_ADDR', '') if request is not None else ''


def _key(username: str, ip: str) -> str:
    digest = hashlib.sha256(f'{(username or "").strip().lower()}|{ip}'.encode()).hexdigest()[:32]
    return f'login-fail:{digest}'


def is_locked(username: str, ip: str) -> bool:
    record = safe_cache_get(_key(username, ip)) or {}
    return record.get('until', 0) > time.time()


def record_failure(username: str, ip: str) -> None:
    key = _key(username, ip)
    record = safe_cache_get(key) or {}
    if record.get('until') and record['until'] <= time.time():
        record = {}  # 잠금이 끝났으면 처음부터 다시 셉니다
    record['count'] = record.get('count', 0) + 1
    if record['count'] >= LIMIT:
        record['until'] = time.time() + LOCK_SECONDS
    safe_cache_set(key, record, LOCK_SECONDS + 60)


def record_success(username: str, ip: str) -> None:
    safe_cache_delete(_key(username, ip))
